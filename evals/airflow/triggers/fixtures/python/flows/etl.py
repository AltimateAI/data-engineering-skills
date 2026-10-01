def extract():
    return [1, 2, 3]


def transform(rows):
    return [r * 2 for r in rows]


def load(rows):
    print(f"loaded {len(rows)}")


if __name__ == "__main__":
    load(transform(extract()))
