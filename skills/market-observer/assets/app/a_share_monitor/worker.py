"""One-shot isolated AKShare worker. Parent process enforces total timeout."""
import sys


def main():
    import akshare as ak
    source, destination = sys.argv[1:]
    frame = ak.stock_zh_a_spot_em() if source == "eastmoney" else ak.stock_zh_a_spot()
    frame.to_json(destination, orient="records", force_ascii=False)


if __name__ == "__main__":
    main()
