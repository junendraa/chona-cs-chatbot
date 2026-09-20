"""
Statistik: isi percakapan (jumlah pesan, topik yang sering ditanyakan)
dan pemakaian API selama sesi (token, waktu respons, sisa kuota Groq).
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

KATA_KUNCI_TOPIK = {
    "Order & PO": ["order", "pesanan", "mesen", "po", "batch", "slot", "join"],
    "Pembayaran": ["bayar", "transfer", "qris", "bca", "kode unik", "lunas", "tagihan", "nominal"],
    "Pengiriman & tracking": ["kirim", "resi", "tracking", "lacak", "posisi", "ongkir", "estimasi", "nyampe", "sampai ke", "sampai di", "belum sampai", "berapa lama", "gudang"],
    "EMS tax & DCO": ["pajak", "tax", "ems", "dco", "bea cukai", "pelunasan"],
    "Refund & komplain": ["refund", "rusak", "komplain", "complain", "salah kirim", "hilang", "kurang", "retur"],
    "Chona Coin & promo": ["coin", "koin", "referral", "gacha", "promo", "diskon", "voucher", "testimoni"],
    "CO Shopee": ["shopee"],
}


def _pola(kata):
    # Kata pendek wajib utuh, supaya "po" tidak cocok dengan "poster".
    if len(kata) <= 3:
        return rf"\b{re.escape(kata)}\b"
    return re.escape(kata)


POLA_TOPIK = {
    topik: re.compile("|".join(_pola(k) for k in daftar), re.IGNORECASE)
    for topik, daftar in KATA_KUNCI_TOPIK.items()
}


def deteksi_topik(teks):
    """Satu pesan bisa masuk lebih dari satu topik."""
    return [topik for topik, pola in POLA_TOPIK.items() if pola.search(teks)]


def ringkas_percakapan(riwayat):
    pertanyaan = [m["content"] for m in riwayat if m["role"] == "user"]
    topik = Counter(t for teks in pertanyaan for t in deteksi_topik(teks))
    return {
        "pesan_user": len(pertanyaan),
        "pesan_bot": len(riwayat) - len(pertanyaan),
        "topik": dict(topik.most_common()),
    }


@dataclass
class StatistikSesi:
    mulai: datetime = field(default_factory=datetime.now)
    request_berhasil: int = 0
    request_gagal: int = 0
    token_prompt: int = 0
    token_jawaban: int = 0
    token_berpikir: int = 0
    total_detik: float = 0.0
    kuota: dict = field(default_factory=dict)

    def catat(self, hasil):
        if hasil.kuota:
            self.kuota = hasil.kuota
        if not hasil.berhasil:
            self.request_gagal += 1
            return
        self.request_berhasil += 1
        self.token_prompt += hasil.token_prompt
        self.token_jawaban += hasil.token_jawaban
        self.token_berpikir += hasil.token_berpikir
        self.total_detik += hasil.durasi_detik

    @property
    def total_token(self):
        return self.token_prompt + self.token_jawaban

    def ringkasan(self):
        """Versi dict untuk disimpan ke file JSON."""
        return {
            "request_berhasil": self.request_berhasil,
            "request_gagal": self.request_gagal,
            "token_prompt": self.token_prompt,
            "token_jawaban": self.token_jawaban,
            "token_berpikir": self.token_berpikir,
            "rata_rata_detik": round(self.total_detik / self.request_berhasil, 2) if self.request_berhasil else 0,
        }


def _angka(n):
    return f"{int(n):,}".replace(",", ".")


def laporan(stat, riwayat):
    isi = ringkas_percakapan(riwayat)
    topik = ", ".join(f"{t} ({n})" for t, n in list(isi["topik"].items())[:3]) or "-"
    menit = int((datetime.now() - stat.mulai).total_seconds() // 60)

    baris = [
        "",
        "📊 Statistik",
        "Percakapan saat ini",
        f"  Pesan kamu        : {isi['pesan_user']}",
        f"  Jawaban Chona     : {isi['pesan_bot']}",
        f"  Topik terbanyak   : {topik}",
        "",
        f"Pemakaian API sejak {stat.mulai:%H:%M} ({menit} menit)",
        f"  Request           : {stat.request_berhasil} berhasil, {stat.request_gagal} gagal",
        f"  Total token       : {_angka(stat.total_token)} "
        f"(prompt {_angka(stat.token_prompt)}, jawaban {_angka(stat.token_jawaban)}, "
        f"termasuk berpikir {_angka(stat.token_berpikir)})",
    ]

    if stat.request_berhasil:
        rata_token = stat.total_token / stat.request_berhasil
        rata_detik = f"{stat.total_detik / stat.request_berhasil:.2f}".replace(".", ",")
        baris.append(f"  Rata-rata         : {_angka(rata_token)} token dan {rata_detik} detik per request")

    k = stat.kuota
    try:
        baris.append(
            f"  Sisa kuota Groq   : {_angka(k['sisa_request'])}/{_angka(k['limit_request'])} request per hari, "
            f"{_angka(k['sisa_token'])}/{_angka(k['limit_token'])} token per menit"
        )
    except (KeyError, TypeError, ValueError):
        pass  # belum ada request, atau header kuota tidak dikirim

    return "\n".join(baris) + "\n"
