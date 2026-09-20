"""
Mengelola conversation history: menyusun konteks yang dikirim ke model,
menyimpan percakapan ke file JSON, dan memuatnya kembali.
"""

import json
from datetime import datetime
from pathlib import Path

import config

PERAN_VALID = {"user", "assistant"}


def bangun_messages(system_prompt, riwayat, maks_giliran=config.MAKS_GILIRAN_KONTEKS):
    """
    Menyusun list messages untuk API: system prompt + potongan riwayat terakhir.

    `riwayat` hanya berisi pesan user & assistant. System prompt sengaja tidak
    disimpan di riwayat, tapi disusun ulang setiap request. Dengan begitu
    perubahan pengaturan (misalnya /panjang) langsung berlaku tanpa /reset.
    """
    # +1 untuk pertanyaan baru yang belum dijawab
    potongan = riwayat[-(maks_giliran * 2 + 1):]

    # Jangan mulai dari jawaban assistant yang pertanyaannya sudah terpotong
    while potongan and potongan[0]["role"] != "user":
        potongan = potongan[1:]

    return [{"role": "system", "content": system_prompt}, *potongan]


def _nama_file_aman(nama):
    # Path(...).name membuang nama folder, jadi "../../rahasia" tidak bisa
    # dipakai untuk menulis atau membaca file di luar folder riwayat/.
    nama = Path(nama.strip()).name
    if not nama:
        return None
    if not nama.lower().endswith(".json"):
        nama += ".json"
    return nama


def simpan(riwayat, *, pengaturan, statistik, nama=None):
    config.FOLDER_RIWAYAT.mkdir(exist_ok=True)
    nama_file = (_nama_file_aman(nama) if nama else None) or f"chat_{datetime.now():%Y%m%d_%H%M%S}.json"
    path = config.FOLDER_RIWAYAT / nama_file

    data = {
        "aplikasi": "Chona CS Chatbot",
        "disimpan_pada": datetime.now().isoformat(timespec="seconds"),
        "pengaturan": pengaturan,
        "statistik": statistik,
        "messages": riwayat,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def daftar_file():
    """File riwayat, yang terbaru di urutan pertama."""
    if not config.FOLDER_RIWAYAT.is_dir():
        return []
    return sorted(config.FOLDER_RIWAYAT.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def muat(pilihan, daftar):
    """
    Memuat percakapan dari nomor urut (sesuai daftar /muat) atau nama file.
    Mengembalikan (path, list pesan). Melempar FileNotFoundError / ValueError.
    """
    if pilihan.isdigit():
        nomor = int(pilihan)
        if not 1 <= nomor <= len(daftar):
            raise FileNotFoundError(f"Tidak ada file nomor {nomor}. Ketik /muat untuk melihat daftar.")
        path = daftar[nomor - 1]
    else:
        nama_file = _nama_file_aman(pilihan)
        path = config.FOLDER_RIWAYAT / nama_file if nama_file else None
        if path is None or not path.is_file():
            raise FileNotFoundError(f"File '{pilihan}' tidak ada di folder riwayat/.")

    try:
        # utf-8-sig juga bisa membaca file JSON yang diawali BOM (sering dari editor Windows)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        raise ValueError(f"File {path.name} rusak atau bukan JSON yang valid.")

    # Format program ini berupa dict dengan kunci "messages". Format notebook
    # contoh dari kelas berupa list langsung, jadi keduanya diterima.
    pesan = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(pesan, list):
        raise ValueError("Format file tidak dikenali.")

    # Pesan berperan "system" dibuang: file riwayat tidak boleh bisa
    # mengganti instruksi dan persona chatbot.
    bersih = [
        {"role": m["role"], "content": m["content"]}
        for m in pesan
        if isinstance(m, dict) and m.get("role") in PERAN_VALID and isinstance(m.get("content"), str)
    ]
    if not bersih:
        raise ValueError("File tidak berisi percakapan.")
    return path, bersih
