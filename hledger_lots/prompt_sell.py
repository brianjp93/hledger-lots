from dataclasses import dataclass

import questionary

from . import avg, fifo, prompt
from .hl import hledger2txn
from .info import LotsInfo


@dataclass
class SellInfo(prompt.Tradeinfo):
    revenue_account: str


class PromptSell(prompt.Prompt):
    def __init__(
        self,
        file: tuple[str, ...],
        avg_cost: bool,
        check: bool,
        no_desc: str | None = None,
        commodity=None,
        date=None,
        quantity=None,
        price=None,
        cash_account=None,
        revenue_account=None,
    ) -> None:
        super().__init__(file, avg_cost, check, no_desc)
        print(self.initial_info)
        self.commodity = commodity
        self.date = date
        self.quantity = quantity
        self.price = price
        self.cash_account = cash_account
        self.revenue_account = revenue_account
        self.info = self.get_info()
        self.last_purchase = self.get_last_purchase(self.info)

    def get_info(self):
        if not self.commodity:
            self.commodity = prompt.select_commodities_text(self.commodities)
        info = next(info for info in self.infos if info["comm"] == self.commodity)
        return info

    def ask_commodity_account(self, info: LotsInfo):
        commodity = info["comm"]
        accts_txt = self.run_hledger("accounts", f"cur:{commodity}")
        accts = [acct for acct in accts_txt.split("\n") if acct != ""]

        answer: str = questionary.select(
            "Commodity Account",
            choices=accts,
            use_shortcuts=True,
        ).ask()
        return answer

    def prompt(self):
        commodity = self.info["comm"]
        sell_date = self.ask_date(self.last_purchase)
        qtty = float(self.ask_sell_qtty(self.info))
        price_str = self.ask_price(self.info)

        if price_str == "":
            value_str = self.ask_total(qtty, self.info)
            value = float(value_str)
            price = value / qtty
        else:
            price = float(price_str)
            value = qtty * price

        cash_acct = self.ask_cash_account()

        if self.avg_cost:
            commodity_acct = self.ask_commodity_account(self.info)
        else:
            commodity_acct = ""

        revenue_acct = self.ask_revenue_account()

        result = SellInfo(
            date=sell_date,
            quantity=qtty,
            commodity=commodity,
            cash_account=cash_acct,
            revenue_account=revenue_acct,
            commodity_account=commodity_acct,
            price=price,
            value=value,
        )

        return result

    def get_hl_txn(self):
        if all((self.date, self.quantity, self.price, self.cash_account, self.revenue_account)):
            sell = SellInfo(
                date=self.date,
                quantity=self.quantity,
                commodity=self.commodity,
                cash_account=self.cash_account,
                revenue_account=self.revenue_account,
                commodity_account="",
                price=self.price,
                value=self.price * self.quantity,
            )
        else:
            sell = self.prompt()
        commodity = sell.commodity
        adj_txns = hledger2txn(self.file, commodity, self.no_desc)

        if self.avg_cost:
            txn_print = avg.avg_sell(
                txns=adj_txns,
                date=sell.date,
                qtty=sell.quantity,
                cur=sell.commodity,
                cash_account=sell.cash_account,
                revenue_account=sell.revenue_account,
                comm_account=sell.commodity_account,
                value=sell.value,
                check=self.check,
            )
        else:
            sell_fifo = fifo.get_sell_lots(
                lots=adj_txns,
                sell_date=sell.date,
                sell_qtty=sell.quantity,
                check=self.check,
            )
            txn_print = fifo.txn2hl(
                txns=sell_fifo,
                date=sell.date,
                cur=sell.commodity,
                cash_account=sell.cash_account,
                revenue_account=sell.revenue_account,
                value=sell.value,
            )

        return txn_print
