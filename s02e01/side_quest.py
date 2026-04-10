from s02e01.main import run, fetch_rows, query

FAKE_CODES = [
    "J",
    "D",
    "I",
    "B",
    "A",
    "C",
    "G",
    "E",
    "H",
    "F",
]

def main():
    """Side quest entry point."""

    rows = fetch_rows()
    for row in rows:
        print(row)

    code_to_idx = {chr(65 + i): i for i in range(10)}
    reorder = [code_to_idx[c] for c in FAKE_CODES]
    items = [rows[i] for i in reorder]

    for item in items:
        print("\n{item}".format(item=item))


    results = run(items=items, with_retries=True)



if __name__ == "__main__":
    main()
