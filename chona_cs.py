"""
Chona CS: chatbot customer service GO BY CHONA di terminal, memakai Groq API.

Jalankan dengan:
    python chona_cs.py

Alur besarnya:
1. Muat API key dari file .env
2. Muat system prompt (persona + pengetahuan toko) dari prompts/system_prompt.md
3. Loop: baca input
   - diawali "/"  -> jalankan perintah (/simpan, /statistik, dst.)
   - selain itu   -> kirim ke Groq bersama riwayat, tampilkan jawaban streaming
"""

import os
import sys
import urllib.parse
from dataclasses import dataclass, field
from getpass import getpass

from dotenv import load_dotenv

import config
import llm
import percakapan
import statistik


# ==========================================
# Tampilan terminal
# ==========================================

PAKAI_WARNA = sys.stdout.isatty() and "NO_COLOR" not in os.environ


def siapkan_terminal():
    """Supaya emoji dan warna tampil benar, terutama di Windows."""
    for aliran in (sys.stdin, sys.stdout):
        try:
            aliran.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if os.name == "nt":
        os.system("")  # menyalakan dukungan kode warna ANSI di console Windows


def warna(teks, kode):
    return f"\033[{kode}m{teks}\033[0m" if PAKAI_WARNA else teks


def info(teks):
    print(warna(teks, "90"))


def sukses(teks):
    print(warna(teks, "32"))


def peringatan(teks):
    print(warna(f"⚠️  {teks}", "33"))


LABEL_KAMU = warna("Kamu  : ", "1;36")
LABEL_CHONA = warna("Chona : ", "1;35")


# ==========================================
# State satu sesi chat
# ==========================================

@dataclass
class Sesi:
    client: object
    system_prompt: str
    model: str = config.MODEL_DEFAULT
    temperature: float = config.TEMPERATURE_DEFAULT
    panjang: str = config.PANJANG_DEFAULT
    stream: bool = True
    riwayat: list = field(default_factory=list)  # hanya pesan user & assistant
    stat: statistik.StatistikSesi = field(default_factory=statistik.StatistikSesi)
    jumlah_pesan_tersimpan: int = 0
    daftar_model: list = field(default_factory=list)

    @property
    def belum_disimpan(self):
        return len(self.riwayat) != self.jumlah_pesan_tersimpan

    def pengaturan(self):
        return {
            "model": self.model,
            "temperature": self.temperature,
            "panjang": self.panjang,
            "stream": self.stream,
        }

    def system_prompt_lengkap(self):
        instruksi = config.PRESET_PANJANG[self.panjang]["instruksi"]
        return f"{self.system_prompt}\n\n# Panjang jawaban\n{instruksi}"


# ==========================================
# Persiapan
# ==========================================

def muat_api_key():
    """API key dibaca dari .env, bukan ditulis di kode. Fallback: input tersembunyi."""
    load_dotenv(config.FOLDER_PROJECT / ".env")
    api_key = os.getenv("GROQ_API_KEY", "").strip()

    if not api_key:
        peringatan("GROQ_API_KEY tidak ditemukan di file .env.")
        info("Salin .env.example menjadi .env lalu isi key-nya, atau tempel key di bawah (tidak akan terlihat).")
        try:
            api_key = getpass("GROQ_API_KEY: ").strip()
        except (EOFError, KeyboardInterrupt):
            api_key = ""

    if not api_key:
        print("Tanpa API key chatbot tidak bisa berjalan.")
        sys.exit(1)
    return api_key


def baca_prompt(nama_file):
    path = config.FOLDER_PROMPT / nama_file
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        print(f"File prompt tidak ditemukan: {path}")
        sys.exit(1)


# ==========================================
# Inti chatbot: kirim pertanyaan, tampilkan jawaban
# ==========================================

def jawab(sesi, pertanyaan):
    sesi.riwayat.append({"role": "user", "content": pertanyaan})
    messages = percakapan.bangun_messages(sesi.system_prompt_lengkap(), sesi.riwayat)

    print(LABEL_CHONA, end="", flush=True)
    sudah_tampil = []

    def tampilkan_potongan(teks):
        sudah_tampil.append(teks)
        print(teks, end="", flush=True)

    hasil = llm.kirim(
        sesi.client,
        messages,
        model=sesi.model,
        temperature=sesi.temperature,
        max_tokens=config.PRESET_PANJANG[sesi.panjang]["max_tokens"],
        stream=sesi.stream,
        saat_potongan=tampilkan_potongan if sesi.stream else None,
    )
    sesi.stat.catat(hasil)

    if hasil.berhasil:
        print("" if sesi.stream else hasil.teks)
        print()
        # Jawaban disimpan supaya jadi konteks di giliran berikutnya
        sesi.riwayat.append({"role": "assistant", "content": hasil.teks})
        if hasil.finish_reason == "length":
            peringatan("Jawaban terpotong karena batas panjang. Coba /panjang panjang.\n")
    else:
        if sudah_tampil:
            print()
        peringatan(hasil.error)
        print()
        # Request gagal: buang pertanyaan tadi supaya riwayat tetap berpasangan
        sesi.riwayat.pop()


# ==========================================
# Perintah khusus
# ==========================================

def simpan_sesi(sesi, nama=None):
    ringkasan = {**statistik.ringkas_percakapan(sesi.riwayat), **sesi.stat.ringkasan()}
    path = percakapan.simpan(sesi.riwayat, nama=nama, pengaturan=sesi.pengaturan(), statistik=ringkasan)
    sesi.jumlah_pesan_tersimpan = len(sesi.riwayat)
    return path.relative_to(config.FOLDER_PROJECT).as_posix()


def perintah_bantuan(sesi, argumen):
    print()
    for sintaks, keterangan in DAFTAR_BANTUAN:
        print(f"  {warna(sintaks.ljust(34), '36')}{keterangan}")
    info("\n  exit dan clear tanpa garis miring juga bisa.\n")


def perintah_keluar(sesi, argumen):
    if sesi.riwayat and sesi.belum_disimpan:
        try:
            info(f"Percakapan disimpan otomatis ke {simpan_sesi(sesi)}")
        except OSError as e:
            peringatan(f"Gagal menyimpan otomatis: {e}")
    print("Makasih sudah mampir, kak! Sampai jumpa 👋")
    return False


def perintah_reset(sesi, argumen):
    jumlah = len(sesi.riwayat)
    sesi.riwayat = []
    sesi.jumlah_pesan_tersimpan = 0
    sukses(f"Riwayat dihapus ({jumlah} pesan). Mulai obrolan baru ya, kak!\n")


def perintah_simpan(sesi, argumen):
    if not sesi.riwayat:
        peringatan("Belum ada percakapan untuk disimpan.")
        return
    try:
        sukses(f"Percakapan disimpan ke {simpan_sesi(sesi, argumen or None)}\n")
    except OSError as e:
        peringatan(f"Gagal menyimpan: {e}")


def perintah_muat(sesi, argumen):
    daftar = percakapan.daftar_file()

    if not argumen:
        if not daftar:
            info("Belum ada file riwayat. Simpan dulu dengan /simpan.")
            return
        print("\nFile riwayat (terbaru di atas):")
        for nomor, path in enumerate(daftar, 1):
            print(f"  {nomor}. {path.name}")
        info("Muat dengan /muat <nomor> atau /muat <nama file>\n")
        return

    try:
        path, pesan = percakapan.muat(argumen, daftar)
    except (OSError, ValueError) as e:  # termasuk file tidak ada & JSON rusak
        peringatan(str(e))
        return

    if sesi.riwayat and sesi.belum_disimpan:
        info(f"Percakapan sebelumnya disimpan dulu ke {simpan_sesi(sesi)}")

    sesi.riwayat = pesan
    sesi.jumlah_pesan_tersimpan = len(pesan)
    sukses(f"Memuat {len(pesan)} pesan dari {path.name}. Pesan terakhir:")
    tampilkan_pesan(pesan[-2:])
    info("Lanjutkan saja percakapannya.\n")


def tampilkan_pesan(daftar_pesan):
    for m in daftar_pesan:
        label = LABEL_KAMU if m["role"] == "user" else LABEL_CHONA
        print(f"{label}{m['content']}\n")


def perintah_riwayat(sesi, argumen):
    if not sesi.riwayat:
        info("Riwayat masih kosong.")
        return
    print()
    tampilkan_pesan(sesi.riwayat)
    info(f"({len(sesi.riwayat)} pesan. Yang dikirim ke model hanya {config.MAKS_GILIRAN_KONTEKS} tanya-jawab terakhir.)\n")


def perintah_statistik(sesi, argumen):
    print(statistik.laporan(sesi.stat, sesi.riwayat))


def perintah_atur(sesi, argumen):
    preset = config.PRESET_PANJANG[sesi.panjang]
    print(
        "\nPengaturan saat ini\n"
        f"  Model       : {sesi.model}\n"
        f"  Temperature : {sesi.temperature}\n"
        f"  Panjang     : {sesi.panjang} (maks {preset['max_tokens']} token)\n"
        f"  Streaming   : {'aktif' if sesi.stream else 'mati'}\n"
        f"  Konteks     : {config.MAKS_GILIRAN_KONTEKS} tanya-jawab terakhir dikirim ke model\n"
    )


def perintah_model(sesi, argumen):
    if not sesi.daftar_model:
        try:
            sesi.daftar_model = llm.daftar_model_chat(sesi.client)
        except Exception as e:
            peringatan(f"Gagal mengambil daftar model. {llm.pesan_error(e)}")

    if not argumen:
        print(f"\nModel aktif: {sesi.model}")
        for nomor, nama in enumerate(sesi.daftar_model, 1):
            penanda = "  ← aktif" if nama == sesi.model else ""
            print(f"  {nomor}. {nama}{penanda}")
        if sesi.daftar_model:
            info("Ganti dengan /model <nomor> atau /model <nama>")
        print()
        return

    if argumen.isdigit():
        nomor = int(argumen)
        if not 1 <= nomor <= len(sesi.daftar_model):
            peringatan("Nomor model tidak ada. Ketik /model untuk melihat daftar.")
            return
        pilihan = sesi.daftar_model[nomor - 1]
    else:
        pilihan = argumen
        if sesi.daftar_model and pilihan not in sesi.daftar_model:
            peringatan(f"Model '{pilihan}' tidak tersedia. Ketik /model untuk melihat daftar.")
            return

    sesi.model = pilihan
    sukses(f"Model diganti ke {pilihan}.\n")


def perintah_suhu(sesi, argumen):
    if not argumen:
        info(f"Temperature sekarang {sesi.temperature}. Contoh: /suhu 0.3  (0 = konsisten, 2 = sangat acak)")
        return
    try:
        nilai = float(argumen.replace(",", "."))
    except ValueError:
        peringatan("Temperature harus berupa angka, contoh: /suhu 0.3")
        return
    if not 0 <= nilai <= 2:
        peringatan("Temperature harus di antara 0 dan 2.")
        return
    sesi.temperature = nilai
    catatan = " Untuk CS, 0.2-0.5 paling aman supaya jawabannya konsisten." if nilai > 1 else ""
    sukses(f"Temperature diatur ke {nilai}.{catatan}\n")


def perintah_panjang(sesi, argumen):
    pilihan = argumen.lower()
    if pilihan not in config.PRESET_PANJANG:
        peringatan(f"Pilih salah satu: {', '.join(config.PRESET_PANJANG)}. Sekarang: {sesi.panjang}.")
        return
    sesi.panjang = pilihan
    sukses(f"Panjang jawaban diatur ke {pilihan}.\n")


def perintah_stream(sesi, argumen):
    pilihan = argumen.lower()
    if pilihan in ("on", "aktif", "nyala"):
        sesi.stream = True
    elif pilihan in ("off", "mati"):
        sesi.stream = False
    elif not pilihan:
        sesi.stream = not sesi.stream
    else:
        peringatan("Gunakan /stream on atau /stream off.")
        return
    sukses(f"Streaming {'aktif' if sesi.stream else 'mati'}.\n")


def perintah_admin(sesi, argumen):
    """Merangkum masalah pembeli jadi pesan WhatsApp siap kirim ke admin manusia."""
    if not any(m["role"] == "user" for m in sesi.riwayat):
        info("Ceritakan dulu masalahnya ke Chona, nanti /admin akan merangkumnya untuk admin.")
        return

    info("Merangkum percakapan untuk admin...")
    transkrip = "\n".join(
        f"{'Pembeli' if m['role'] == 'user' else 'Bot CS'}: {m['content']}"
        for m in sesi.riwayat[-20:]
    )
    messages = [
        {"role": "system", "content": baca_prompt("ringkasan_admin.md")},
        {"role": "user", "content": transkrip},
    ]
    # Temperature rendah: ringkasan tidak boleh menambah informasi baru
    hasil = llm.kirim(sesi.client, messages, model=sesi.model, temperature=0.2, max_tokens=700, stream=False)
    sesi.stat.catat(hasil)

    if not hasil.berhasil:
        peringatan(hasil.error)
        info(f"Kamu tetap bisa chat admin langsung: https://wa.me/{config.NOMOR_WA_ADMIN}\n")
        return

    ringkasan = hasil.teks.strip()
    tautan = f"https://wa.me/{config.NOMOR_WA_ADMIN}?text={urllib.parse.quote(ringkasan)}"
    print(f"\n{ringkasan}\n")
    sukses("Buka tautan ini untuk mengirimnya ke admin lewat WhatsApp:")
    print(f"{tautan}\n")


DAFTAR_BANTUAN = [
    ("/bantuan", "Tampilkan daftar perintah ini"),
    ("/keluar", "Selesai (percakapan otomatis disimpan)"),
    ("/reset", "Hapus riwayat, mulai obrolan baru"),
    ("/simpan [nama]", "Simpan percakapan ke folder riwayat/"),
    ("/muat [nomor|nama]", "Lihat daftar file, atau lanjutkan percakapan lama"),
    ("/riwayat", "Tampilkan isi percakapan saat ini"),
    ("/statistik", "Jumlah pesan, topik, token, dan sisa kuota"),
    ("/admin", "Ringkas masalahmu jadi pesan WhatsApp untuk admin"),
    ("/atur", "Lihat pengaturan saat ini"),
    ("/model [nomor|nama]", "Lihat atau ganti model LLM"),
    ("/suhu <0-2>", "Atur temperature"),
    ("/panjang <pendek|sedang|panjang>", "Atur panjang jawaban"),
    ("/stream <on|off>", "Nyalakan atau matikan streaming"),
]

PERINTAH = {
    "bantuan": perintah_bantuan, "help": perintah_bantuan,
    "keluar": perintah_keluar, "exit": perintah_keluar, "quit": perintah_keluar,
    "reset": perintah_reset, "clear": perintah_reset,
    "simpan": perintah_simpan, "save": perintah_simpan,
    "muat": perintah_muat, "load": perintah_muat,
    "riwayat": perintah_riwayat, "history": perintah_riwayat,
    "statistik": perintah_statistik, "stats": perintah_statistik,
    "admin": perintah_admin,
    "atur": perintah_atur, "settings": perintah_atur,
    "model": perintah_model,
    "suhu": perintah_suhu, "temperature": perintah_suhu, "temp": perintah_suhu,
    "panjang": perintah_panjang, "length": perintah_panjang,
    "stream": perintah_stream,
}

# Perintah dari contoh di kelas, boleh diketik tanpa garis miring
PERINTAH_TANPA_GARIS_MIRING = {"exit", "quit", "keluar", "clear", "reset"}


def proses_input(sesi, teks):
    """Mengembalikan False kalau chatbot harus berhenti."""
    kata = teks.split(maxsplit=1)
    nama = kata[0].lower()

    if nama.startswith("/") or (len(kata) == 1 and nama in PERINTAH_TANPA_GARIS_MIRING):
        nama = nama.lstrip("/")
        argumen = kata[1].strip() if len(kata) > 1 else ""
        fungsi = PERINTAH.get(nama)
        if fungsi is None:
            peringatan(f"Perintah /{nama} tidak dikenal. Ketik /bantuan untuk daftar perintah.")
            return True
        return fungsi(sesi, argumen) is not False

    if len(teks) > config.MAKS_PANJANG_PESAN:
        peringatan(f"Pesan terlalu panjang ({len(teks)} karakter). Maksimal {config.MAKS_PANJANG_PESAN}.")
        return True

    jawab(sesi, teks)
    return True


# ==========================================
# Program utama
# ==========================================

def tampilkan_pembuka(sesi):
    garis = "=" * 58
    print(warna(garis, "35"))
    print(warna("   CHONA CS · Customer Service GO BY CHONA", "1;35"))
    print(warna(garis, "35"))
    info(
        f"Model {sesi.model} · temperature {sesi.temperature} · "
        f"jawaban {sesi.panjang} · streaming {'aktif' if sesi.stream else 'mati'}"
    )
    info("Ketik /bantuan untuk daftar perintah, /keluar untuk selesai.\n")
    # Salam pembuka hanya dicetak, tidak dimasukkan ke riwayat, supaya tidak
    # ikut dikirim (dan memakan token) di setiap request.
    print(f"{LABEL_CHONA}Halo kak! Aku Chona, CS virtual GO BY CHONA 😊 "
          "Mau tanya soal order, pembayaran, tracking, EMS tax, atau refund?\n")


def main():
    siapkan_terminal()
    sesi = Sesi(
        client=llm.buat_client(muat_api_key()),
        system_prompt=baca_prompt("system_prompt.md"),
    )
    tampilkan_pembuka(sesi)

    while True:
        try:
            # Karakter BOM (\ufeff) bisa terbawa di awal input kalau program dijalankan lewat pipe di Windows
            teks = input(LABEL_KAMU).replace("\ufeff", "").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            perintah_keluar(sesi, "")
            break

        if not teks:
            continue
        if not proses_input(sesi, teks):
            break


if __name__ == "__main__":
    main()
