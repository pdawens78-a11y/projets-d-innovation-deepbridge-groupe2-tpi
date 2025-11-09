import csv

def read_csv_to_dict(filename):
    """
    return csv file as dict
    """
    with open(filename, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        data = {col: [] for col in reader.fieldnames}
        for row in reader:
            for col in reader.fieldnames:
                data[col].append(row[col])
    return data

def get_column_names(dataset):
    """
    Returns column names list
    """
    return list(dataset.keys())

def normalize_column_names(dataset, new_col_names):
    """
    return dataset dict with normalized column names.
    """
    old_col_names = list(dataset.keys())
    if len(new_col_names) != len(old_col_names):
        raise ValueError("Length of new_col_names must match existing columns")
    
    new_dataset = {}
    for old_col, new_col in zip(old_col_names, new_col_names):
        new_dataset[new_col] = dataset[old_col]
    return new_dataset

def print_dataset(dataset):
    """
    Print the entire dataset row by row, col by col.
    """
    cols = get_column_names(dataset)
    row_count = len(dataset[cols[0]]) if cols else 0

    print("Dataset:")
    print(" | ".join(cols))
    print("-" * 20)
    for i in range(row_count):
        print(" | ".join(dataset[col][i] for col in cols))

def print_one_row(dataset, row_idx):
    """
    Print a single row from the dataset by index.
    """
    cols = get_column_names(dataset)
    row_count = len(dataset[cols[0]])
    if row_idx < 0 or row_idx >= row_count:
        print(f"Row index {row_idx} out of range")
        return
    
    print(f"Row {row_idx}:")
    for col in cols:
        print(f"{col}: {dataset[col][row_idx]}")

def print_one_col(dataset, col_name):
    """
    Print a single column from the dataset by column name.
    """
    if col_name not in dataset:
        print(f"Column '{col_name}' not found")
        return
    print(f"Column '{col_name}':")
    for val in dataset[col_name]:
        print(val)

def main():
    filename = "input.csv"
    data = read_csv_to_dict(filename)
    
    print("\noriginal columns:")
    print(get_column_names(data))
    
    print("\nprint full dataset:")
    print_dataset(data)
    
    # normalize column names
    new_names = [col.lower().replace(" ", "_") for col in get_column_names(data)]
    data_normalized = normalize_column_names(data, new_names)
    
    print("\nNormalized columns:")
    print(get_column_names(data_normalized))
    
    print("\nPrint one row (row 0):")
    print_one_row(data_normalized, 0)
    
    print("\nPrint one column ('numéro' or 'numero' depending on original):")
    col_to_print = new_names[0] 
    print_one_col(data_normalized, col_to_print)

def read_csv_to_dict(filename):
    with open(filename, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        data = {col: [] for col in reader.fieldnames}
        for row in reader:
            for col in reader.fieldnames:
                data[col].append(row[col])
    return data

# Cleaning functions
def clean_double(values):
    cleaned = []
    for v in values:
        try:
            v_clean = v.strip().replace(",", ".")
            cleaned.append(float(v_clean))
        except:
            cleaned.append(None)
    return cleaned

def clean_boolean(values):
    cleaned = []
    for v in values:
        if isinstance(v, str):
            v_lower = v.strip().lower()
            if v_lower in ("1", "true", "yes", "y"):
                cleaned.append(1)
            elif v_lower in ("0", "false", "no", "n", "x", ""):
                cleaned.append(0)
            elif v_lower not in ("", "nan", "null", "none"):
                cleaned.append(1)
            else:
                cleaned.append(None)
        else:
            cleaned.append(None)
    return cleaned

def clean_age(values):
    return clean_double(values)

def clean_sex(values):
    return clean_boolean(values)

def clean_generic_int(values):
    cleaned = []
    for v in values:
        try:
            cleaned.append(int(float(v)))
        except:
            cleaned.append(None)
    return cleaned

def clean_generic_str(values):
    return [v.strip() if isinstance(v, str) else "" for v in values]

def clean_deepbridge_dataset(filename):
    target_variables = [
        "cplction N (stroke + periph)", "AIT/AVC", "cplction C", "cplication J30", "Hématomes"
    ]

    features = [
        "Numéro", "Age calcul", "Age arrondi", "femme/homme", "S+", "patch = 1, eversion = 2",
        "shunt", "Arterio", "re inter", "Anomalie", "Anomalie comm"
    ]
    
    target_variables = [col.lower().replace(" ", "_") for col in target_variables]
    features = [col.lower().replace(" ", "_") for col in features]
    
    raw_data = read_csv_to_dict(filename)
    
    new_names = [col.strip().lower().replace(" ", "_") for col in get_column_names(raw_data)]
    data_normalized = normalize_column_names(raw_data, new_names)
    
    columns_to_process = features + target_variables
    
    dataset = {}
    
    for col in columns_to_process:
        values = data_normalized.get(col, [])
        if col in ("Age calcul", "Age arrondi"):
            dataset[col] = clean_age(values)
        elif col == "femme/homme":
            dataset[col] = clean_sex(values)
        elif col in ("patch_=_1,_eversion_=_2"):
            dataset[col] = clean_generic_int(values)
        elif col in ("s+", "shunt", "arterio", "re_inter", "anomalie", "anomalie_comm"):
            dataset[col] = clean_boolean(values)
        elif col in target_variables:
            dataset[col] = clean_boolean(values)
        else:
            dataset[col] = clean_generic_str(values)
    
    n_rows = len(dataset[features[0]]) if features else 0
    complication = []
    for i in range(n_rows):
        flag = 0
        for target_col in target_variables:
            val = dataset[target_col][i]
            if val is not None and val != 0:
                flag = 1
                break
                
        complication.append(flag)
    
    dataset["complication"] = complication
    
    for col in target_variables:
        dataset.pop(col, None)
    
    return dataset

def export_dict_to_csv(dataset, filename):
    """
    Export a dataset dict to a csv
    """
    columns = list(dataset.keys())
    n_rows = len(dataset[columns[0]]) if columns else 0
    
    with open(filename, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # header
        writer.writerow(columns)
        
        # rows
        for i in range(n_rows):
            row = [dataset[col][i] for col in columns]
            writer.writerow(row)


if __name__ == "__main__":
    filename = "input.csv"
    
    clean_data = clean_deepbridge_dataset(filename)
    export_dict_to_csv(clean_data, "deep-bridge-data-clean.csv")
