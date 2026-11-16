"""Print cash balance and positions for every account.  Usage: python draft/account.py"""
from webull.trade.trade_client import TradeClient

from _client import make_client


def main():
    trade = TradeClient(make_client())
    for acct in trade.account_v2.get_account_list().json():
        acct_id = acct["account_id"]
        print(f"Account …{acct_id[-4:]}  {acct.get('account_label')}")

        balance = trade.account_v2.get_account_balance(acct_id).json()
        print(f"  total cash {balance['total_cash_balance']} / market value {balance['total_market_value']}"
              f" ({balance['total_asset_currency']})")
        for cur in balance.get("account_currency_assets", []):
            print(f"  {cur['currency']}: cash {cur['cash_balance']}  market value {cur['market_value']}"
                  f"  buying power {cur['buying_power']}  unrealized P/L {cur['unrealized_profit_loss']}")

        positions = trade.account_v2.get_account_position(acct_id).json()
        print(f"  positions: {len(positions)}")
        for pos in positions:
            print(f"    {pos}")


if __name__ == "__main__":
    main()
