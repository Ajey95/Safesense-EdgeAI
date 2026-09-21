"""Train and release a 100x48 INT8 TFLite HAR model from WISDOM traces."""
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from ml.preprocessing.wisdom48 import CLASS_NAMES, build_split

SAFESENSE_CLASSES = ("vacant", "stationary", "walking")

def sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024*1024), b""): digest.update(chunk)
    return digest.hexdigest()


def require_all_classes(name: str, labels: np.ndarray, classes: tuple[str, ...]) -> None:
    observed = set(labels.tolist())
    expected = set(range(len(classes)))
    if observed != expected:
        missing = [classes[index] for index in sorted(expected - observed)]
        raise SystemExit(f"{name} split is incomplete; missing classes: {missing}")


def trace_hashes(root: Path, groups: list[str]) -> dict[str, str]:
    return {group: sha256(root / group) for group in sorted(set(groups))}


def safesense_labels(x: np.ndarray, y: np.ndarray, groups: list[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Keep only states SafeSense is authorized to emit; jumping remains UNKNOWN."""
    keep = y != 4
    mapped = y[keep].copy()
    mapped[np.isin(mapped, [1, 2, 3])] = 1
    mapped[mapped == 5] = 2
    return x[keep], mapped, [group for group, accepted in zip(groups, keep) if accepted]


def locations(raw: str) -> set[str]:
    return {value.strip() for value in raw.split(",") if value.strip()}


def cache_split(cache: np.lib.npyio.NpzFile, desired_locations: set[str]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    xs = [cache[f"x_{partition}"] for partition in ("train", "validation", "test")]
    ys = [cache[f"y_{partition}"] for partition in ("train", "validation", "test")]
    groups = sum((cache[f"groups_{partition}"].tolist() for partition in ("train", "validation", "test")), [])
    x, y = np.concatenate(xs), np.concatenate(ys)
    keep = np.asarray([Path(group).name.split("_", 1)[0] in desired_locations for group in groups])
    return x[keep], y[keep], [group for group, accepted in zip(groups, keep) if accepted]


def balanced_representative_indices(labels: np.ndarray, limit: int = 300) -> np.ndarray:
    """Select deterministic calibration samples spanning every output class."""
    classes = np.unique(labels)
    per_class = max(1, limit // len(classes))
    selected: list[np.ndarray] = []
    for label in classes:
        candidates = np.flatnonzero(labels == label)
        count = min(per_class, len(candidates))
        selected.append(candidates[np.linspace(0, len(candidates) - 1, count, dtype=int)])
    return np.concatenate(selected)

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("ml/models/wisdom48_int8"))
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--epochs", type=int, default=45)
    parser.add_argument("--task", choices=("wisdom6", "safesense3"), default="wisdom6")
    parser.add_argument("--train-locations", default="lab,corridor")
    parser.add_argument("--validation-locations", default="parking")
    parser.add_argument("--test-locations", default="yard")
    parser.add_argument("--no-validation", action="store_true")
    parser.add_argument("--development-no-holdout", action="store_true", help="Train a labelled demo artifact on all selected data; never eligible for release.")
    parser.add_argument("--physics-synthetic-ratio", type=float, default=0.0)
    args=parser.parse_args()
    try:
        import tensorflow as tf
    except ImportError as error:
        raise SystemExit("TensorFlow is required. Install the project ML extra before training.") from error
    tf.keras.utils.set_random_seed(20260919)
    # Whole locations are held out: no windows from any recording leak across partitions.
    if args.cache:
        with np.load(args.cache) as cache:
            x_train, y_train, train_groups = cache_split(cache, locations(args.train_locations))
            x_val, y_val, val_groups = cache_split(cache, locations(args.validation_locations))
            x_test, y_test, test_groups = cache_split(cache, locations(args.test_locations))
    else:
        x_train,y_train,train_groups=build_split(args.data,locations(args.train_locations))
        x_val,y_val,val_groups=build_split(args.data,locations(args.validation_locations))
        x_test,y_test,test_groups=build_split(args.data,locations(args.test_locations))
    classes = CLASS_NAMES
    if args.task == "safesense3":
        x_train, y_train, train_groups = safesense_labels(x_train, y_train, train_groups)
        x_val, y_val, val_groups = safesense_labels(x_val, y_val, val_groups)
        x_test, y_test, test_groups = safesense_labels(x_test, y_test, test_groups)
        classes = SAFESENSE_CLASSES
    if args.development_no_holdout:
        # Explicitly use the train partition for in-sample reporting only. This is
        # useful for a software demo, never for a production release claim.
        x_test, y_test, test_groups = x_train, y_train, train_groups
    require_all_classes("training", y_train, classes); require_all_classes("test", y_test, classes)
    if not args.no_validation: require_all_classes("validation", y_val, classes)
    if args.physics_synthetic_ratio:
        if args.task != "safesense3":
            raise SystemExit("physics augmentation currently supports the three SafeSense classes only")
        from ml.augmentation.physics_csi import synthesize_from_training
        synthetic_x, synthetic_y = synthesize_from_training(x_train, y_train, args.physics_synthetic_ratio)
        x_train = np.concatenate((x_train, synthetic_x))
        y_train = np.concatenate((y_train, synthetic_y))
    mean=x_train.mean(axis=(0,1), keepdims=True).astype(np.float32); std=x_train.std(axis=(0,1), keepdims=True).astype(np.float32)
    std[std < 1e-6]=1.0
    normalize=lambda x: ((x-mean)/std).astype(np.float32)
    x_train,x_val,x_test=normalize(x_train)[...,None],normalize(x_val)[...,None],normalize(x_test)[...,None]
    # Strided convolutions bound the largest INT8 activation to 25*12*8 bytes,
    # leaving practical headroom in the firmware's 64 KiB TFLM tensor arena.
    model=tf.keras.Sequential([
        tf.keras.layers.Input((100,48,1)),
        tf.keras.layers.Conv2D(8,3,strides=(2,2),activation="relu",padding="same"),
        tf.keras.layers.Conv2D(16,3,strides=(2,2),activation="relu",padding="same"),
        tf.keras.layers.GlobalAveragePooling2D(),
        tf.keras.layers.Dense(16,activation="relu"),
        tf.keras.layers.Dense(len(classes),activation="softmax"),
    ])
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3),loss="sparse_categorical_crossentropy",metrics=["accuracy"])
    callbacks=[] if args.no_validation else [tf.keras.callbacks.EarlyStopping(monitor="val_loss",patience=5,restore_best_weights=True)]
    fit_kwargs={} if args.no_validation else {"validation_data": (x_val, y_val)}
    class_counts=np.bincount(y_train,minlength=len(classes))
    class_weights={label:len(y_train)/(len(classes)*count) for label,count in enumerate(class_counts)}
    model.fit(x_train,y_train,epochs=args.epochs,batch_size=32,class_weight=class_weights,callbacks=callbacks,verbose=2,**fit_kwargs)
    float_predicted=np.argmax(model.predict(x_test,batch_size=64,verbose=0),axis=1)
    float_metrics={"accuracy":accuracy_score(y_test,float_predicted),"macro_f1":f1_score(y_test,float_predicted,average="macro"),"confusion_matrix":confusion_matrix(y_test,float_predicted,labels=range(len(classes))).tolist()}
    args.output.mkdir(parents=True,exist_ok=True)
    saved=args.output/"saved_model.keras"; model.save(saved)
    np.savez(args.output/"normalization.npz",mean=mean.reshape(48),std=std.reshape(48))
    converter=tf.lite.TFLiteConverter.from_keras_model(model); converter.optimizations=[tf.lite.Optimize.DEFAULT]
    representative_indices=balanced_representative_indices(y_train)
    converter.representative_dataset=lambda: ([x_train[index:index+1]] for index in representative_indices)
    converter.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]; converter.inference_input_type=tf.int8; converter.inference_output_type=tf.int8
    tflite=args.output/"wisdom48_int8.tflite"; tflite.write_bytes(converter.convert())
    interpreter=tf.lite.Interpreter(model_path=str(tflite)); interpreter.allocate_tensors(); details=interpreter.get_input_details()[0],interpreter.get_output_details()[0]
    in_scale,in_zero=details[0]["quantization"]; out_scale,out_zero=details[1]["quantization"]
    predicted=[]
    for sample in x_test:
        quantized=np.clip(np.round(sample/in_scale+in_zero),-128,127).astype(np.int8)[None,...]
        interpreter.set_tensor(details[0]["index"],quantized); interpreter.invoke(); output=interpreter.get_tensor(details[1]["index"])[0]
        predicted.append(int(np.argmax((output.astype(np.float32)-out_zero)*out_scale)))
    int8_metrics={"accuracy":accuracy_score(y_test,predicted),"macro_f1":f1_score(y_test,predicted,average="macro"),"confusion_matrix":confusion_matrix(y_test,predicted,labels=range(len(classes))).tolist()}
    calibration_counts={classes[label]:int(np.sum(y_train[representative_indices] == label)) for label in range(len(classes))}
    metrics={"status":"DEVELOPMENT_ONLY_NO_HELD_OUT_EVALUATION" if args.development_no_holdout else "CANDIDATE","task":args.task,"physics_synthetic":{"ratio":args.physics_synthetic_ratio,"training_windows":len(synthetic_y) if args.physics_synthetic_ratio else 0,"test_data":"real and untouched"},"protocol":{"train_locations":sorted(locations(args.train_locations)),"validation_locations":[] if args.no_validation else sorted(locations(args.validation_locations)),"test_locations":[] if args.development_no_holdout else sorted(locations(args.test_locations)),"validation_used":not args.no_validation,"in_sample_reporting":args.development_no_holdout},"accuracy":int8_metrics["accuracy"],"macro_f1":int8_metrics["macro_f1"],"float_metrics":float_metrics,"int8_metrics":int8_metrics,"quantization_delta":{"accuracy":int8_metrics["accuracy"]-float_metrics["accuracy"],"macro_f1":int8_metrics["macro_f1"]-float_metrics["macro_f1"]},"training_class_weights":{classes[label]:weight for label,weight in class_weights.items()},"calibration":{"samples":len(representative_indices),"class_counts":calibration_counts},"samples":{"train":len(y_train),"validation":0 if args.no_validation else len(y_val),"test":len(y_test)},"groups":{"train":sorted(set(train_groups)),"validation":[] if args.no_validation else sorted(set(val_groups)),"test":sorted(set(test_groups))},"trace_sha256":{"train":trace_hashes(args.data,train_groups),"validation":{} if args.no_validation else trace_hashes(args.data,val_groups),"test":trace_hashes(args.data,test_groups)},"classes":classes,"shape":[100,48,1],"input_dtype":details[0]["dtype"].__name__,"output_dtype":details[1]["dtype"].__name__,"tflite_bytes":tflite.stat().st_size,"tflite_sha256":sha256(tflite),"created_at":datetime.now(timezone.utc).isoformat()}
    (args.output/"release_manifest.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    print(json.dumps(metrics,indent=2))

if __name__ == "__main__": main()
