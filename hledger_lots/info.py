import csv
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from io import StringIO
from typing import TypedDict
from textwrap import dedent

from tabulate import tabulate

from .lib import AdjustedTxn, get_files_comm, get_xirr


class LotsInfo(TypedDict):
    comm: str
    cur: str
    qtty: str
    amount: str
    avg_cost: str
    mkt_price: str | None
    mkt_amount: str | None
    mkt_profit: str | None
    mkt_date: str | None
    xirr: str | None


@dataclass
class Price:
    date: date
    comm: str
    price: float
    cur: str


LAST_PRICE_DICT: dict[str, tuple[date, float]] = {}


def get_last_price_dict(files_comm: list[str]):
    if LAST_PRICE_DICT:
        return LAST_PRICE_DICT
    prices_comm = [
        "hledger",
        *files_comm,
        "prices",
        "--show-reverse",
    ]
    prices_proc = subprocess.run(prices_comm, capture_output=True)
    prices_str = prices_proc.stdout.decode("utf8")
    if not prices_str:
        return {}
    for d_string, commodity, price in re.findall(
        r'(\d+-\d+-\d+) "?([^\s"]+)"?[^\d]*(\d+\.\d+)', prices_str
    ):
        comm = commodity.upper()
        if comm not in LAST_PRICE_DICT:
            last_date = datetime.strptime(d_string, "%Y-%m-%d").date()
            LAST_PRICE_DICT[comm] = (last_date, float(price))
        else:
            new_date = datetime.strptime(d_string, "%Y-%m-%d").date()
            old_date, _ = LAST_PRICE_DICT[comm]
            if new_date > old_date:
                LAST_PRICE_DICT[comm] = (new_date, float(price))
    return LAST_PRICE_DICT


def get_last_price(files_comm: list[str], commodity: str):
    price_dict = get_last_price_dict(files_comm)
    output = price_dict.get(commodity.upper(), (None, None))
    return output


def get_commodities(journals: tuple[str, ...]):
    files_comm = get_files_comm(journals)
    comm = ["hledger", *files_comm, "commodities"]
    commodities_proc = subprocess.run(comm, capture_output=True)
    commodities_str = commodities_proc.stdout.decode("utf8")

    commodities_list = [com for com in commodities_str.split("\n") if com != ""]
    return commodities_list


class Info:
    def __init__(
        self,
        journals: tuple[str, ...],
        commodity: str,
        txns: list[AdjustedTxn],
        no_desc: str | None = None,
    ) -> None:
        self.journals = journals
        self.files_comm = get_files_comm(journals)
        self.commodity = commodity.upper()
        self.txns = txns

        self.has_txn = len(self.txns) > 0
        self.last_price = get_last_price(self.files_comm, commodity)

        self.market_date, self.market_price = self.last_price

    def get_lots_xirr(self, last_buy_date: date):
        if self.market_date and self.market_price and self.market_date >= last_buy_date:
            xirr = get_xirr(self.market_price, self.market_date, self.txns)
            return xirr

    def get_info_txt(self, info: LotsInfo):
        info_txt = dedent(f"""\
            Info
            ----
            Commodity:      {info["comm"]}
            Quantity:       {info["qtty"]}
            Amount:         {info["amount"]}
            Average Cost:   {info["avg_cost"]}
        """)

        if self.market_date or self.market_price:
            info_txt += dedent(f"""\
                Market Price:  {info["mkt_price"]}
                Market Amount: {info["mkt_amount"]}
                Market Profit: {info["mkt_profit"]}
                Market Date:   {info["mkt_date"]}
                Xirr:          {info["xirr"]} (APR 30/360US)
            """)
        else:
            info_txt += "\nMarket Data not available"

        return info_txt


class AllInfo:
    def __init__(self, journals: tuple[str, ...], no_desc: str) -> None:
        self.journals = journals
        self.no_desc = no_desc
        self.commodities = get_commodities(journals)

    def get_infos_table(self, infos: list[LotsInfo], output_format: str):
        infos_list = [info for info in infos]
        infos_sorted = sorted(
            infos_list, key=lambda info: info["xirr"] or "", reverse=True
        )
        table = tabulate(
            infos_sorted,
            headers="keys",
            numalign="decimal",
            floatfmt=",.4f",
            tablefmt=output_format,
        )
        return table

    def get_infos_csv(self, infos: list[LotsInfo]):
        infos_list = [info for info in infos]
        infos_sorted = sorted(
            infos_list, key=lambda info: info["xirr"] or "", reverse=True
        )

        fieldnames = infos_sorted[0].keys()
        infos_io = StringIO()
        writer = csv.DictWriter(infos_io, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(infos_sorted)
        infos_io.seek(0)
        return infos_io
