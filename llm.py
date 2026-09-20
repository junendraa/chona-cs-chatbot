"""
Semua komunikasi dengan Groq API ada di file ini.

Bagian lain program cukup memanggil kirim() dan menerima HasilJawaban.
kirim() tidak pernah melempar exception: kalau gagal, alasannya ada di
hasil.error, sehingga program utama tidak akan crash.
"""

import time
from dataclasses import dataclass, field

import groq
from groq import Groq

import config


@dataclass
class HasilJawaban:
    teks: str = ""
    error: str | None = None
    finish_reason: str | None = None
    token_prompt: int = 0
    token_jawaban: int = 0
    token_berpikir: int = 0
    durasi_detik: float = 0.0
    kuota: dict = field(default_factory=dict)

    @property
    def berhasil(self):
        return self.error is None


def buat_client(api_key):
    """Client adalah 'gerbang' ke server Groq. SDK otomatis mencoba ulang
    request yang gagal sementara (misalnya rate limit) sebanyak MAKS_RETRY."""
    return Groq(api_key=api_key, timeout=config.TIMEOUT_DETIK, max_retries=config.MAKS_RETRY)


def _parameter_tambahan(model):
    # gpt-oss "berpikir" dulu sebelum menjawab, dan token berpikirnya ikut
    # memakan kuota. Pertanyaan CS umumnya sederhana, jadi cukup sedikit.
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": "low"}
    # Qwen menulis proses berpikirnya (<think>...</think>) langsung di dalam
    # jawaban kalau tidak diminta untuk disembunyikan.
    if model.startswith("qwen/"):
        return {"reasoning_format": "hidden"}
    return {}


def _baca_kuota(headers):
    """Groq mengirim sisa kuota di header HTTP setiap respons."""
    return {
        "sisa_request": headers.get("x-ratelimit-remaining-requests"),
        "limit_request": headers.get("x-ratelimit-limit-requests"),
        "sisa_token": headers.get("x-ratelimit-remaining-tokens"),
        "limit_token": headers.get("x-ratelimit-limit-tokens"),
    }


def _isi_token(hasil, usage):
    if usage is None:
        return
    hasil.token_prompt = usage.prompt_tokens or 0
    hasil.token_jawaban = usage.completion_tokens or 0
    detail = getattr(usage, "completion_tokens_details", None)
    hasil.token_berpikir = getattr(detail, "reasoning_tokens", 0) or 0


def pesan_error(e):
    """Menerjemahkan exception dari SDK Groq menjadi pesan yang dimengerti pengguna."""
    # Urutan pengecekan penting: APITimeoutError adalah turunan APIConnectionError.
    if isinstance(e, groq.AuthenticationError):
        return "API key ditolak Groq. Cek lagi GROQ_API_KEY di file .env."
    if isinstance(e, groq.RateLimitError):
        tunggu = e.response.headers.get("retry-after")
        saran = f" Coba lagi dalam {tunggu} detik." if tunggu else " Tunggu sebentar lalu coba lagi."
        return "Kuota Groq sedang habis (rate limit)." + saran
    if isinstance(e, groq.APITimeoutError):
        return f"Groq tidak merespons dalam {config.TIMEOUT_DETIK} detik. Coba kirim ulang."
    if isinstance(e, groq.APIConnectionError):
        return "Tidak bisa terhubung ke Groq. Cek koneksi internet."
    if isinstance(e, groq.NotFoundError):
        return "Model tidak ditemukan. Ketik /model untuk melihat model yang tersedia."
    if isinstance(e, groq.BadRequestError):
        detail = str(getattr(e, "message", e))[:200]
        return f"Permintaan ditolak Groq: {detail}"
    if isinstance(e, groq.APIStatusError):
        return f"Server Groq sedang bermasalah (HTTP {e.status_code}). Coba lagi sebentar."
    return f"Error tak terduga: {type(e).__name__}: {e}"


def kirim(client, messages, *, model, temperature, max_tokens, stream=True, saat_potongan=None):
    """
    Mengirim messages ke Groq dan mengembalikan HasilJawaban.

    Kalau stream=True, jawaban diterima potongan demi potongan dan setiap
    potongan langsung diteruskan ke fungsi `saat_potongan` (dipakai untuk
    mencetak jawaban kata per kata di terminal).
    """
    hasil = HasilJawaban()
    mulai = time.perf_counter()

    try:
        # with_raw_response dipakai supaya header HTTP (sisa kuota) ikut terbaca.
        respons_mentah = client.chat.completions.with_raw_response.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            stream=stream,
            **_parameter_tambahan(model),
        )
        hasil.kuota = _baca_kuota(respons_mentah.headers)
        respons = respons_mentah.parse()

        if stream:
            potongan = []
            try:
                for chunk in respons:
                    if chunk.choices:
                        pilihan = chunk.choices[0]
                        teks = pilihan.delta.content or ""
                        if teks:
                            potongan.append(teks)
                            if saat_potongan:
                                saat_potongan(teks)
                        if pilihan.finish_reason:
                            hasil.finish_reason = pilihan.finish_reason
                    # Jumlah token hanya dikirim Groq di potongan terakhir.
                    x_groq = getattr(chunk, "x_groq", None)
                    if x_groq is not None and x_groq.usage is not None:
                        _isi_token(hasil, x_groq.usage)
            finally:
                respons.close()
            hasil.teks = "".join(potongan)
        else:
            pilihan = respons.choices[0]
            hasil.teks = pilihan.message.content or ""
            hasil.finish_reason = pilihan.finish_reason
            _isi_token(hasil, respons.usage)

    except KeyboardInterrupt:
        hasil.error = "Jawaban dibatalkan (Ctrl+C)."
    except Exception as e:
        hasil.error = pesan_error(e)

    hasil.durasi_detik = time.perf_counter() - mulai

    if hasil.berhasil and not hasil.teks.strip():
        hasil.error = "Model mengembalikan jawaban kosong. Coba kirim ulang atau /panjang panjang."
    return hasil


# Model di akun Groq yang bukan untuk chat teks (suara, moderasi, dll.)
_BUKAN_MODEL_CHAT = ("whisper", "orpheus", "guard", "compound", "allam")


def daftar_model_chat(client):
    semua = client.models.list().data
    return sorted(m.id for m in semua if not any(kata in m.id for kata in _BUKAN_MODEL_CHAT))
