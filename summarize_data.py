import pandas as pd
import os
import glob


def summarize_excel(file_path):
    print(f"### File: {os.path.basename(file_path)}")
    try:
        # According to the project spec, core files have header at row 1 (0-indexed),
        # but let's just inspect what's there
        if "supporting datasets" in file_path.replace("\\", "/"):
            df = pd.read_excel(file_path, header=0)
        else:
            df = pd.read_excel(file_path, header=1)

        print(f"- **Rows:** {df.shape[0]}, **Columns:** {df.shape[1]}")
        print("- **Columns:** " + ", ".join(df.columns.astype(str).tolist()))
        print("- **Sample Data:**")
        print("```text")
        print(df.head(2).to_string(index=False))
        print("```")
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    print("\n")


def main():
    base_dir = r"c:\Users\amit0\OneDrive\Desktop\nifty100_datasets\n100"
    files = glob.glob(os.path.join(base_dir, "**", "*.xlsx"), recursive=True)
    for f in sorted(files):
        summarize_excel(f)


if __name__ == "__main__":
    main()
