import streamlit as st
from streamlit_option_menu import option_menu
from fpdf import FPDF
import datetime
import json
import uuid

# Google Sheets libs
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GS_AVAILABLE = True
except Exception:
    GS_AVAILABLE = False

# optional imports for metadata
try:
    import requests
except Exception:
    requests = None

# try to use client-side JS (streamlit_javascript) for reliable userAgent/ip
try:
    from streamlit_javascript import st_javascript
    SJ_AVAILABLE = True
except Exception:
    SJ_AVAILABLE = False

current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Nilai Tes Anda', 0, 1, 'C')


# -------------------------
# Google Sheets helpers
# -------------------------
def connect_gsheets_from_secrets():
    if not GS_AVAILABLE:
        return None, "gspread/oauth2client tidak terpasang"
    if "gspread" not in st.secrets:
        return None, "st.secrets['gspread'] tidak ditemukan"

    creds_json = None
    if "service_account_json" in st.secrets["gspread"]:
        try:
            creds_json = json.loads(st.secrets["gspread"]["service_account_json"])
        except Exception as e:
            return None, f"Invalid service_account_json: {e}"
    elif "service_account_b64" in st.secrets["gspread"]:
        try:
            import base64
            raw = base64.b64decode(st.secrets["gspread"]["service_account_b64"]).decode("utf-8")
            creds_json = json.loads(raw)
        except Exception as e:
            return None, f"Invalid service_account_b64: {e}"
    else:
        return None, "Tidak menemukan service_account_json atau service_account_b64 di st.secrets"

    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
    except Exception as e:
        return None, f"Gagal authorisasi gspread: {e}"

    try:
        sheet_key = st.secrets["gspread"]["sheet_key"]
        sh = client.open_by_key(sheet_key)
        ws = sh.sheet1
        return ws, None
    except Exception as e:
        return None, f"Gagal buka sheet: {e}"


def append_row_safe(ws, row):
    try:
        ws.append_row(row, value_input_option="USER_ENTERED")
        return True, None
    except Exception as e:
        return False, str(e)


# -------------------------
# Metadata & conversion helpers
# -------------------------
def get_session_id():
    if "sid" not in st.session_state:
        st.session_state.sid = str(uuid.uuid4())
    return st.session_state.sid


def get_user_agent():
    """
    Try client-side JS first (st_javascript). If not available, return 'unknown'.
    """
    if SJ_AVAILABLE:
        try:
            ua = st_javascript("navigator.userAgent")
            return ua if ua else "unknown"
        except Exception:
            return "unknown"
    return "unknown"


def get_public_ip():
    """
    Attempt client-side fetch using st_javascript for most reliability on Streamlit Cloud.
    Fallback: use requests (server-side). If both unavailable, return 'unknown'.
    """
    # 1) try st_javascript client-side fetch (returns string ip)
    if SJ_AVAILABLE:
        try:
            js_code = """
            (async ()=>{
              try {
                const r = await fetch('https://api.ipify.org?format=json');
                const j = await r.json();
                return j.ip;
              } catch(e) {
                return null;
              }
            })();
            """
            ip = st_javascript(js_code)
            if ip:
                return ip
        except Exception:
            pass

    # 2) fallback to requests (server-side)
    if requests is not None:
        try:
            r = requests.get("https://api.ipify.org?format=json", timeout=3)
            return r.json().get("ip", "unknown")
        except Exception:
            pass

    return "unknown"


def toefl_to_ielts(score):
    mapping = [
        (660, 9.0),
        (640, 8.5),
        (620, 8.0),
        (600, 7.5),
        (580, 7.0),
        (560, 6.5),
        (540, 6.0),
        (520, 5.5),
        (500, 5.0),
        (480, 4.5),
        (460, 4.0),
        (440, 3.5),
        (310, 3.0),
    ]
    try:
        s = float(score)
    except:
        return None
    for minimum, band in mapping:
        if s >= minimum:
            return band
    return 0.0


# -------------------------
# UI & App
# -------------------------
st.set_page_config(page_title="Aplikasi Konversi Skor TBI", layout="centered")

# Sidebar: connection status
with st.sidebar:
    st.header("Status :")
    if not GS_AVAILABLE:
        st.warning("gspread/oauth2client belum terpasang. Tambahkan ke requirements.txt")
        st.stop()
    ws, err = connect_gsheets_from_secrets()
    if ws:
        st.success("Ready")
    else:
        st.error(f"GSheets not connected: {err}")
    st.markdown("---")
    st.info("Pastikan data Nama diisi dengan benar.")

# navigation
with st.sidebar:
    selected = option_menu('Hitung Nilai Hasil CAT',
                           ['Hitung Nilai TPA', 'Hitung Nilai TBI'],
                           default_index=1)

# ---------- TPA (left untouched) ----------
if (selected == 'Hitung Nilai TPA'):
    st.title('Hitung Nilai TPA')

    nama = st.text_input("Nama")
    nilai_verbal = st.text_input("Masukkan Nilai Verbal", "0")
    nilai_numerikal = st.text_input("Masukkan Nilai Numerikal", "0")
    nilai_figural = st.text_input("Masukkan Nilai Figural", "0")

    Hitung = st.button('Hitung Nilai TPA')

    if Hitung:
        # validasi input
        try:
            nv = float(nilai_verbal)
            nn = float(nilai_numerikal)
            nf = float(nilai_figural)
        except Exception:
            st.error("Pastikan semua input numeric (angka).")
            st.stop()

        rata_rata = (nv + nn + nf) / 3
        nilai_tpa = ((rata_rata / 100) * 600) + 200
        st.markdown(f'<p style="font-size: 24px;">Nilai TPA Anda Adalah= {round(nilai_tpa, 2)}</p>',
                    unsafe_allow_html=True)

        # Simpan hasil dalam PDF
        pdf = PDF()
        pdf.add_page()
        pdf.set_font("Courier", size=12)
        try:
            pdf.image("logopusbinjf.png", x=10, y=8, w=25)
        except Exception:
            pass
        pdf.cell(200, 10, f" ", ln=True, align="C")
        pdf.cell(50, 10, "Nama: ")
        pdf.cell(50, 10, str(nama))
        pdf.cell(200, 10, f" ", ln=True)
        pdf.set_font("Courier", "B", 12)
        pdf.cell(50, 10, "Subtest", 1, 0, "C")
        pdf.cell(50, 10, "Nilai", 1, 0, "C")
        pdf.ln()
        pdf.set_font("Courier", size=12)
        pdf.cell(50, 10, "Verbal", 1)
        pdf.cell(50, 10, str(nv), 1, 0, "C")
        pdf.ln()
        pdf.cell(50, 10, "Numerikal", 1)
        pdf.cell(50, 10, str(nn), 1, 0, "C")
        pdf.ln()
        pdf.cell(50, 10, "Figural", 1)
        pdf.cell(50, 10, str(nf), 1, 0, "C")
        pdf.ln()
        pdf.cell(50, 10, "Skor TPA", 1)
        pdf.cell(50, 10, f"{round(nilai_tpa, 2)}", 1, 0, "C")
        pdf.ln()
        pdf.set_font("Courier", size=11)
        pdf.cell(20, 5, "Note : hasil tes ini bersifat try out, tidak dapat digunakan untuk mengikuti", 0)
        pdf.ln()
        pdf.cell(20, 5, "       seleksi beasiswa apapun", 0)
        pdf.ln()
        pdf.cell(200, 50, "Best Regards,", ln=True, align="C")
        pdf.cell(200, 10, "Pusbin JFPM", ln=True, align="C")
        pdf.set_y(0)
        pdf.cell(0, 10, f"Dicetak: {current_date}", 0, 0, "R")
        pdf_output = pdf.output(dest="S").encode("latin1")

        st.download_button(
            label="Download Hasil Perhitungan TPA (PDF)",
            data=pdf_output,
            file_name="hasil_perhitungan_tpa.pdf",
            mime="application/pdf"
        )

        # TPA record kept as before
        record = [
            current_date,
            "TPA",
            nama,
            nv,
            nn,
            nf,
            round(nilai_tpa, 2),
            str(uuid.uuid4())
        ]
        if ws:
            ok, err = append_row_safe(ws, record)
            if ok:
                st.success("Hasil konversi.")
            else:
                st.error(f"Gagal : {err}")
        else:
            st.info("Tidak tersambung, hasil hanya diunduh PDF.")


# ---------- TBI (UPDATED: show only name, toefl score, ielts; include ielts in PDF) ----------
if (selected == "Hitung Nilai TBI"):
    st.title('Hitung Nilai TBI')

    # Nilai & konversi arrays (unchanged)
    nilai_listening = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72, 74, 76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 100]
    konversi_listening = [31, 32, 32, 33, 34, 35, 35, 36, 37, 38, 38, 39, 40, 41, 41, 42, 43, 44, 44, 45, 46, 47, 47, 48, 49, 50, 50, 51, 52, 52, 53, 54, 55, 55, 56, 57, 58, 58, 59, 60, 61, 61, 62, 63, 64, 64, 65, 66, 67, 67, 68]
    nilai_structure = [0, 2.5, 5, 7.5, 10, 12.5, 15, 17.5, 20, 22.5, 25, 27.5, 30, 32.5, 35, 37.5, 40, 42.5, 45, 47.5, 50, 52.5, 55, 57.5, 60, 62.5, 65, 67.5, 70, 72.5, 75, 77.5, 80, 82.5, 85, 87.5, 90, 92.5, 95, 97.5, 100]
    konversi_structure = [31, 32, 33, 34, 35, 36, 37, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 62, 63, 64, 65, 66, 67, 68]
    nilai_reading = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72, 74, 76, 78, 80, 82, 84, 86, 88, 90, 92, 94, 96, 98, 100]
    konversi_reading = [31,	32,	32,	33,	34,	35,	35,	36,	37,	37,	38,	39,	40,	40,	41,	42,	43,	43,	44,	45,	45,	46,	47,	48,	48,	49,	50,	50,	51,	52,	53,	53,	54,	55,	55,	56,	57,	58,	58,	59,	60,	61,	61,	62,	63,	63,	64,	65,	66,	66,	67]

    konversi_dict = {
        'Listening': dict(zip(nilai_listening, konversi_listening)),
        'Structure': dict(zip(nilai_structure, konversi_structure)),
        'Reading': dict(zip(nilai_reading, konversi_reading))
    }

    def konversi_nilai(variabel, nilai_asli):
        # tolerant nearest-neighbor lookup (keamanan input)
        if variabel == "Listening":
            keys = nilai_listening
            conv = konversi_listening
        elif variabel == "Structure":
            keys = nilai_structure
            conv = konversi_structure
        elif variabel == "Reading":
            keys = nilai_reading
            conv = konversi_reading
        else:
            raise KeyError("Variabel konversi tidak dikenali")
        try:
            val = float(nilai_asli)
        except:
            raise KeyError("Nilai input bukan angka")
        if val in keys:
            return conv[keys.index(val)]
        # nearest neighbor
        nearest_idx = min(range(len(keys)), key=lambda i: abs(keys[i] - val))
        return conv[nearest_idx]

    nama = st.text_input("Nama")
    nilai_input = st.text_input("Masukkan Nilai Listening", "0")
    nilai_input1 = st.text_input("Masukkan Nilai Structure", "0")
    nilai_input2 = st.text_input("Masukkan Nilai Reading", "0")

    # We use a form to reduce rerun flicker — results persist in session_state
    with st.form(key="form_tbi"):
        submitted = st.form_submit_button("Hitung Nilai TBI")

        if submitted:
            # convert inputs
            try:
                n1 = float(nilai_input)
                n2 = float(nilai_input1)
                n3 = float(nilai_input2)
            except Exception:
                st.error("Pastikan semua input numeric (angka).")
                st.stop()

            try:
                nk1 = konversi_nilai('Listening', n1)
                nk2 = konversi_nilai('Structure', n2)
                nk3 = konversi_nilai('Reading', n3)
            except KeyError:
                st.error("Nilai tidak valid untuk konversi. Pastikan memasukkan nilai yang sesuai pilihan.")
                st.stop()

            nilai_akhir = (nk1 + nk2 + nk3) / 3 * 10

            # calculate ielts and metadata AFTER we have toefl-like score
            nilai_ielts_est = toefl_to_ielts(round(nilai_akhir))
            kategori_cefr = None
            # determine kategori (CEFR)
            if 627 <= round(nilai_akhir) <= 677:
                kategori_cefr = "C1 : Effective Operational Proficiency / Advanced (Proficient User)"
            elif 543 <= round(nilai_akhir) <= 626:
                kategori_cefr = "B2 : Vantage / Upper Intermediate (Independent User)"
            elif 460 <= round(nilai_akhir) <= 542:
                kategori_cefr = "B1 : Threshold/Intermediate (Independent User)"
            elif 310 <= round(nilai_akhir) <= 459:
                kategori_cefr = "A2: Waystage / Elementary (Basic User)"
            else:
                kategori_cefr = "Skor tidak termasuk dalam kategori yang diberikan"

            # metadata (still collected for sheet, but NOT shown in UI)
            sid = get_session_id()
            user_agent = get_user_agent()
            ip = get_public_ip()
            timestamp = datetime.datetime.utcnow().isoformat()

            # build PDF (so user can download). include IELTS estimate in PDF.
            pdf = PDF()
            pdf.add_page()
            pdf.set_font("Courier", size=12)
            try:
                pdf.image("logopusbinjf.png", x=10, y=8, w=25)
            except Exception:
                pass
            pdf.cell(200, 10, f" ", ln=True, align="C")
            pdf.cell(50, 10, "Nama: ")
            pdf.cell(50, 10, str(nama))
            pdf.cell(200, 10, f" ", ln=True)
            pdf.set_font("Courier", "B", 12)
            pdf.cell(50, 10, "Subtest", 1, 0, "C")
            pdf.cell(50, 10, "Nilai Konversi", 1, 0, "C")
            pdf.ln()
            pdf.set_font("Courier", size=12)
            pdf.cell(50, 10, "Listening", 1)
            pdf.cell(50, 10, str(nk1), 1, 0, "C")
            pdf.ln()
            pdf.cell(50, 10, "Structure", 1)
            pdf.cell(50, 10, str(nk2), 1, 0, "C")
            pdf.ln()
            pdf.cell(50, 10, "Reading", 1)
            pdf.cell(50, 10, str(nk3), 1, 0, "C")
            pdf.ln()
            pdf.cell(50, 10, "Skor TBI (TOEFL)", 1)
            pdf.cell(50, 10, f"{round(nilai_akhir, 2)}", 1, 0, "C")
            pdf.ln()
            pdf.cell(50, 10, "Perkiraan IELTS: ")
            pdf.cell(50, 10, str(nilai_ielts_est))
            pdf.ln()
            pdf.cell(30, 10, "Kategori :", 0)
            pdf.cell(150, 10, str(kategori_cefr), 0)
            pdf.ln()
            pdf.set_font("Courier", size=11)
            pdf.cell(20, 5, "Note : hasil tes ini bersifat try out, tidak dapat digunakan untuk mengikuti", 0)
            pdf.ln()
            pdf.cell(20, 5, "       seleksi beasiswa apapun", 0)
            pdf.ln()
            pdf.set_font("Courier", size=12)
            pdf.cell(200, 50, "Best Regards,", ln=True, align="C")
            pdf.cell(200, 10, "Pusbin JFPM", ln=True, align="C")
            pdf.set_y(0)
            pdf.cell(0, 10, f"Dicetak: {current_date}", 0, 0, "R")
            pdf_output = pdf.output(dest="S").encode("latin1")

            # save persistent result + pdf bytes
            st.session_state["last_tbi_result"] = {
                "timestamp": timestamp,
                "nama": nama,
                "nilai_akhir": round(nilai_akhir, 2),
                "nilai_ielts_est": nilai_ielts_est,
                "kategori_cefr": kategori_cefr,
                "sid": sid,
                "user_agent": user_agent,
                "ip": ip,
                "uuid": str(uuid.uuid4()),
                "pdf_bytes": pdf_output
            }

            # append to sheet (with metadata) — sid/ip still recorded
            record = [
                timestamp,
                "TBI",
                nama,
                nk1,
                nk2,
                nk3,
                round(nilai_akhir, 2),
                nilai_ielts_est,
                kategori_cefr,
                sid,
                user_agent,
                ip,
                st.session_state["last_tbi_result"]["uuid"]
            ]
            if ws:
                ok, err = append_row_safe(ws, record)
                if ok:
                    st.success("Hasil konversi.")
                else:
                    st.error(f"Gagal : {err}")
            else:
                st.info("Tidak tersambung — hasil hanya diunduh PDF.")

    # end form

    # Display persistent result (if any) — show only name, toefl score, ielts; hide sid/ip
    if "last_tbi_result" in st.session_state:
        res = st.session_state["last_tbi_result"]
        st.markdown("### Hasil Terakhir (TBI)")
        st.write(f"Nama: **{res['nama']}**")
        st.write(f"Perkiraan TOEFL: **{res['nilai_akhir']}**")
        st.write(f"Perkiraan IELTS: **{res['nilai_ielts_est']}**")
        st.write(f"Kategori CEFR: {res['kategori_cefr']}")
        st.write("---")
        # Provide download button if pdf bytes present
        if res.get("pdf_bytes"):
            st.download_button(
                label="Download Hasil Perhitungan TBI (PDF)",
                data=res["pdf_bytes"],
                file_name="hasil_perhitungan_tbi.pdf",
                mime="application/pdf"
            )


# optional background
def add_bg_from_url():
    st.markdown(
        f"""
         <style>
         .stApp {{
             background-image: url("https://cdn.pixabay.com/photo/2016/10/11/21/43/geometric-1732847_640.jpg");
             background-attachment: fixed;
             background-size: cover
         }}
         </style>
         """,
        unsafe_allow_html=True
    )


add_bg_from_url()




