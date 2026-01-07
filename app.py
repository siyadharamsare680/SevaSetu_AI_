import os
import re
import cv2
import fitz
import pytesseract
from flask import Flask, render_template, request, redirect, url_for, send_file
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from werkzeug.utils import secure_filename

# ---------------- APPLICATION SETUP ----------------
app = Flask(__name__)

BASE_UPLOAD_DIR = "uploads"
SUPPORTED_FORMATS = {"pdf", "png", "jpg", "jpeg"}

os.makedirs(BASE_UPLOAD_DIR, exist_ok=True)
app.config["UPLOAD_FOLDER"] = BASE_UPLOAD_DIR

# Uncomment ONLY if tesseract is not detected automatically
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ---------------- FILE VALIDATION ----------------
def is_supported(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in SUPPORTED_FORMATS


# ---------------- IMAGE PREPARATION ----------------
def enhance_for_ocr(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    binary = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 2
    )
    return binary


# ---------------- OCR LOGIC ----------------
def extract_text_from_image(image_path):
    img = cv2.imread(image_path)
    processed_img = enhance_for_ocr(img)

    config = "--oem 3 --psm 6"
    text = pytesseract.image_to_string(
        processed_img,
        lang="eng+hin+mar",
        config=config
    )
    return text


def extract_text_from_pdf(pdf_path):
    content = ""
    document = fitz.open(pdf_path)

    for index, page in enumerate(document):
        pixmap = page.get_pixmap(dpi=300)
        temp_img = f"{pdf_path}_{index}.png"
        pixmap.save(temp_img)

        content += extract_text_from_image(temp_img) + "\n"
        os.remove(temp_img)

    return content


# ---------------- DATA INTERPRETATION ----------------
def parse_extracted_data(text):
    result = {
        "name": "",
        "dob": "",
        "gender": "",
        "address": "",
        "id_number": ""
    }

    sanitized_text = re.sub(r"[|]", " ", text)
    lines = [line.strip() for line in sanitized_text.split("\n") if len(line.strip()) > 2]

    # Date of Birth patterns
    dob_regex = [
        r"\b\d{2}[/-]\d{2}[/-]\d{4}\b",
        r"\b\d{4}[/-]\d{2}[/-]\d{2}\b",
        r"\b\d{2}\s[A-Za-z]{3,9}\s\d{4}\b"
    ]

    for line in lines:
        for pattern in dob_regex:
            match = re.search(pattern, line)
            if match:
                result["dob"] = match.group()
                break
        if result["dob"]:
            break

    # Gender detection
    for line in lines:
        lower = line.lower()
        if "male" in lower:
            result["gender"] = "Male"
            break
        elif "female" in lower:
            result["gender"] = "Female"
            break
        elif "transgender" in lower:
            result["gender"] = "Transgender"
            break

    # Aadhaar / PAN extraction
    aadhaar_match = re.search(r"\b\d{4}\s\d{4}\s\d{4}\b", sanitized_text)
    pan_match = re.search(r"\b[A-Z]{5}\d{4}[A-Z]\b", sanitized_text)

    if aadhaar_match:
        result["id_number"] = aadhaar_match.group()
    elif pan_match:
        result["id_number"] = pan_match.group()

    # Name identification
    ignore_terms = {"government", "india", "address", "birth", "male", "female"}
    for line in lines:
        if any(word in line.lower() for word in ignore_terms):
            continue
        if re.match(r"^[A-Z][a-z]+(\s[A-Z][a-z]+)+$", line):
            result["name"] = line
            break

    # Address capture
    address_block = []
    start = False
    for line in lines:
        if "address" in line.lower():
            start = True
            continue
        if start:
            if len(line.split()) < 2:
                break
            address_block.append(line)
            if len(address_block) >= 3:
                break

    result["address"] = ", ".join(address_block)

    return result


# ---------------- ROUTES ----------------
@app.route("/")
def home():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def handle_upload():
    if "files" not in request.files:
        return redirect(url_for("home"))

    uploaded_files = request.files.getlist("files")
    merged_text = ""

    for file in uploaded_files:
        if file and is_supported(file.filename):
            safe_name = secure_filename(file.filename)
            full_path = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
            file.save(full_path)

            if safe_name.lower().endswith(".pdf"):
                merged_text += extract_text_from_pdf(full_path)
            else:
                merged_text += extract_text_from_image(full_path)

    extracted_data = parse_extracted_data(merged_text)

    return render_template(
        "dashboard.html",
        data=extracted_data,
        raw_text=merged_text
    )


@app.route("/download", methods=["POST"])
def generate_pdf():
    output_path = "filled_form.pdf"
    pdf = canvas.Canvas(output_path, pagesize=A4)

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(150, 800, "Government Service Application Form")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, 750, f"Name: {request.form.get('name', '')}")
    pdf.drawString(50, 720, f"DOB: {request.form.get('dob', '')}")
    pdf.drawString(50, 690, f"Gender: {request.form.get('gender', '')}")
    pdf.drawString(50, 660, f"Address: {request.form.get('address', '')}")
    pdf.drawString(50, 630, f"ID Number: {request.form.get('id_number', '')}")

    pdf.drawString(50, 580, "Auto-filled and verified using SevaSetu AI")

    pdf.save()
    return send_file(output_path, as_attachment=True)


# ---------------- APPLICATION ENTRY ----------------
if __name__ == "__main__":
    app.run(debug=True)





