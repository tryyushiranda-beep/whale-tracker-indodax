import os
import json
import requests
from datetime import datetime

# Mengambil API Key Etherscan dari GitHub Secrets
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY")

# 1. DATABASE WALLET TARGET (Daftar alamat wallet smart money/whale yang dipantau)
WATCHED_WALLETS = {
    "0xae2fc9370923e328d4d843776d63d6b1d4ef633d": {"name": "Smart Whale #1", "min_buy_usd": 1000},
    "0x95222290dd7278aa3ddd389cc1e1d165cc4bafe5": {"name": "Insider Fund Alpha", "min_buy_usd": 2000},
    "0x1234567890abcdef1234567890abcdef12345678": {"name": "Top Memecoin Trader", "min_buy_usd": 500}
}

SIGNALS_FILE = "signals.json"

def get_indodax_pairs():
    """
    Mengambil daftar seluruh koin yang terdaftar di Indodax secara real-time.
    """
    indodax_tokens = {}
    try:
        url = "https://indodax.com/api/pairs"
        res = requests.get(url, timeout=10).json()
        for pair in res:
            base_currency = pair.get('base_currency', '').upper()
            pair_id = pair.get('id', '')
            if base_currency and pair_id:
                indodax_tokens[base_currency] = pair_id
    except Exception as e:
        print(f"Gagal mengambil daftar koin Indodax: {e}")
    return indodax_tokens

def load_existing_signals():
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_signals(signals_data):
    with open(SIGNALS_FILE, "w") as f:
        json.dump(signals_data[:50], f, indent=2)

def check_token_safety(contract_address):
    """Mengecek likuiditas & harga token via DexScreener API secara otomatis."""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{contract_address}"
        res = requests.get(url, timeout=5).json()
        if res.get('pairs'):
            pair = res['pairs'][0]
            liquidity = pair.get('liquidity', {}).get('usd', 0)
            price_usd = float(pair.get('priceUsd', 0))
            return liquidity, price_usd
    except Exception as e:
        print(f"Peringatan cek likuiditas: {e}")
    return 0, 0

def process_wallet_tracker():
    signals = load_existing_signals()
    new_found = False

    # 1. Ambil daftar koin aktif Indodax
    indodax_coins = get_indodax_pairs()
    print(f"Total koin terdeteksi di Indodax: {len(indodax_coins)} koin.")

    for wallet_addr, meta in WATCHED_WALLETS.items():
        url = f"https://api.etherscan.io/api?module=account&action=tokentx&address={wallet_addr}&page=1&offset=5&sort=desc&apikey={ETHERSCAN_API_KEY}"
        try:
            res = requests.get(url, timeout=10).json()
            if res.get('status') == '1':
                for tx in res['result']:
                    tx_hash = tx.get('hash')
                    to_addr = tx.get('to', '').lower()
                    from_addr = tx.get('from', '').lower()
                    token_symbol = tx.get('tokenSymbol', '').upper()
                    token_contract = tx.get('contractAddress')
                    
                    # FILTER KHUSUS INDODAX:
                    # Jika simbol token TIDAK ada di Indodax, lewati (abaikan sinyal)
                    if token_symbol not in indodax_coins:
                        continue
                    
                    indodax_pair_id = indodax_coins[token_symbol]

                    # Identifikasi Tipe Transaksi: BUY atau SELL
                    action_type = None
                    if to_addr == wallet_addr.lower():
                        action_type = "BUY"
                    elif from_addr == wallet_addr.lower():
                        action_type = "SELL"

                    # Cek apakah transaksi belum pernah dicatat
                    if action_type and not any(s['hash'] == tx_hash for s in signals):
                        decimals = int(tx.get('tokenDecimal', 18) or 18)
                        amount = int(tx.get('value')) / (10 ** decimals)
                        
                        # Verifikasi Keamanan Token & Harga
                        liquidity, price = check_token_safety(token_contract)
                        est_value_usd = amount * price

                        # Filter nominal transaksi minimum
                        if est_value_usd < meta["min_buy_usd"] and est_value_usd > 0:
                            continue

                        signal_entry = {
                            "id": tx_hash,
                            "hash": tx_hash,
                            "action": action_type,
                            "wallet_name": meta["name"],
                            "token": token_symbol,
                            "amount": f"{amount:,.2f}",
                            "est_val_usd": f"${est_value_usd:,.2f}" if est_value_usd > 0 else "N/A",
                            "liquidity_usd": f"${liquidity:,.0f}" if liquidity > 0 else "N/A",
                            "indodax_pair": indodax_pair_id,
                            "indodax_link": f"https://indodax.com/market/{token_symbol}IDR",
                            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                            "explorer": f"https://etherscan.io/tx/{tx_hash}",
                            "dex_chart": f"https://dexscreener.com/ethereum/{token_contract}"
                        }
                        
                        signals.insert(0, signal_entry)
                        new_found = True
        except Exception as e:
            print(f"Gagal memproses wallet {meta['name']}: {e}")

    if new_found:
        save_signals(signals)
        print("Sinyal Indodax baru berhasil diproses dan disimpan.")

if __name__ == "__main__":
    process_wallet_tracker()
