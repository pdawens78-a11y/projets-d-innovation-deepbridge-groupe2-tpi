import pandas as pd
from clean_csv import clean_deepbridge_dataset, export_dict_to_csv
from randomForest import prepare_features_targets, train_random_forest
from skl2onnx.common.data_types import FloatTensorType

def export_onnx(model, n_features, onnx_path):
    """
    Exporte un modèle RandomForest entraîné au format ONNX,
    avec les mêmes types de sortie (int64 label + float vector probabilities).
    """
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    initial_type = [("input", FloatTensorType([None, n_features]))]

    # zipmap=False ensures vector probabilities instead of a dict
    onnx_model = convert_sklearn(
        model,
        initial_types=initial_type,
        options={id(model): {"zipmap": False}},
        target_opset=12,  # stable opset
    )

    with open(onnx_path, "wb") as f:
        f.write(onnx_model.SerializeToString())

    print(f"Modèle ONNX exporté vers {onnx_path}")


def main():
    raw_csv = "input.csv"
    cleaned_csv = "deep-bridge-data-clean.csv"
    onnx_path = "random_forest_model.onnx"

    print("[1/3] Cleaning raw CSV...")
    dataset = clean_deepbridge_dataset(raw_csv)
    export_dict_to_csv(dataset, cleaned_csv)
    print(f"cleaned data saved to {cleaned_csv}")

    print("[2/3] Training Random Forest model...")
    df = pd.read_csv(cleaned_csv)
    X, y = prepare_features_targets(df)
    run = train_random_forest(X, y)

    print("\n[3/3] Exporting ONNX model...")
    export_onnx(run['model'], n_features=X.shape[1], onnx_path=onnx_path)
    print(f"ONNX model saved to {onnx_path}")


if __name__ == "__main__":
    main()
