"""
Semua pengaturan chatbot dikumpulkan di sini, supaya mengganti model,
temperature, atau batas riwayat cukup di satu tempat.
"""

from pathlib import Path

FOLDER_PROJECT = Path(__file__).resolve().parent
FOLDER_PROMPT = FOLDER_PROJECT / "prompts"
FOLDER_RIWAYAT = FOLDER_PROJECT / "riwayat"

# ==========================================
# Model & parameter LLM
# ==========================================

# gpt-oss-20b dipilih sebagai default karena cepat dan kuota gratisnya longgar
# (1.000 request/hari). Bisa diganti saat chat dengan perintah /model.
MODEL_DEFAULT = "openai/gpt-oss-20b"

# Customer service butuh jawaban konsisten dan faktual, jadi temperature
# sengaja rendah. Nilai 0.7 seperti chatbot umum membuat kebijakan toko
# bisa dijelaskan berbeda-beda tiap kali ditanya.
TEMPERATURE_DEFAULT = 0.4

# Tiap preset mengatur dua hal: batas token dari sisi API (rem darurat)
# dan instruksi ke model (supaya jawabannya memang ditulis sependek itu).
# Untuk gpt-oss, token "berpikir" ikut dihitung dalam batas ini.
PRESET_PANJANG = {
    "pendek": {
        "max_tokens": 400,
        "instruksi": "Jawab sangat singkat, maksimal 2 kalimat.",
    },
    "sedang": {
        "max_tokens": 800,
        "instruksi": "Jawab ringkas: 2-4 kalimat, atau poin singkat kalau berupa langkah-langkah.",
    },
    "panjang": {
        "max_tokens": 1600,
        "instruksi": "Boleh menjawab detail dan bertahap kalau memang dibutuhkan.",
    },
}
PANJANG_DEFAULT = "sedang"

# ==========================================
# Riwayat percakapan
# ==========================================

# LLM tidak punya memori, jadi riwayat dikirim ulang di setiap request.
# Kalau semua riwayat dikirim, token per request terus membengkak dan kuota
# cepat habis. Maka hanya N tanya-jawab terakhir yang dikirim ke model.
MAKS_GILIRAN_KONTEKS = 6

# Pesan yang terlalu panjang ditolak sebelum dikirim, supaya satu tempelan
# teks raksasa tidak menghabiskan kuota token per menit.
MAKS_PANJANG_PESAN = 2000

# ==========================================
# Koneksi & bisnis
# ==========================================

TIMEOUT_DETIK = 30
MAKS_RETRY = 2

NOMOR_WA_ADMIN = "6282165846592"
