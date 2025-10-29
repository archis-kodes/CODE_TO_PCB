### TEMPORARY FILE
# Arduino to compile
# Compile to OPENAI Agent
# OPENAI Agent to Terminal

## OPENAI Agent to pcbgen
## pcbgen to output

from flask import Flask, request, jsonify, send_from_directory, send_file
import os
import shutil
from openai_agent import analyze_code  # your dynamic agent
import json
# Removed pcbgen import since it doesn't exist

app = Flask(__name__)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.route("/upload", methods=["POST"])
def upload_ino():
    if "file" not in request.files:
        return jsonify({"status": "failed", "error": "No file uploaded"}), 400

    file = request.files["file"]
    filepath = os.path.join(UPLOAD_DIR, file.filename)
    file.save(filepath)


    pcb_data = None
    pcb_data = analyze_code(filepath, prompt="")
        
    # Print the OpenAI agent output to terminal
    print("\n" + "="*50)
    print("OPENAI AGENT OUTPUT:")
    print("="*50)
    print(pcb_data)
    print("="*50 + "\n")

    with open(r"C:\Users\Archisman\Videos\codetopcb\backend\pcbgen\design.json", "w") as output:
        json.dump(pcb_data, output, indent=4)

    command = rf'powershell -Command "& \"C:\Program Files\KiCad\6.0\bin\python.exe\" \"C:\Users\Archisman\Videos\codetopcb\backend\pcbgen\pcbgen.py\" \"C:\Users\Archisman\Videos\codetopcb\backend\pcbgen\design.json\" {file.filename}"'

    stat = os.system(command)
    print(stat)
    
    # Check if the folder and .kicad_pcb file exist
    folder_path = os.path.join("C:\\Users\\Archisman\\Videos\\codetopcb", file.filename)
    kicad_pcb_file = os.path.join(folder_path, f"{file.filename}.kicad_pcb")
    
    # After generating the KiCad file
    folder_path = os.path.join("C:\\Users\\Archisman\\Videos\\codetopcb", file.filename)
    kicad_pcb_file = os.path.join(folder_path, f"{file.filename}.kicad_pcb")

    if os.path.exists(kicad_pcb_file):
        print(f"✅ KiCad PCB file generated at: {kicad_pcb_file}")

        # Instead of returning the file, return a JSON response with a download URL
        return jsonify({
            "status": "success",
            "message": "PCB Generated Successfully!",
            "download_url": f"/download/{file.filename}"
        })
    else:
        print(f"❌ KiCad PCB file not found at: {kicad_pcb_file}")
        return jsonify({
            "status": "failed",
            "error": "KiCad PCB file not generated."
       }), 500


# Optional: serve frontend directly from Flask
@app.route("/")
def serve_index():
    return send_from_directory("frontend", "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory("frontend", path)

@app.route("/download/<filename>", methods=["GET"])
def download_pcb(filename):
    folder_path = os.path.join("C:\\Users\\Archisman\\Videos\\codetopcb", filename)
    kicad_pcb_file = os.path.join(folder_path, f"{filename}.kicad_pcb")

    if os.path.exists(kicad_pcb_file):
        print(f"Serving download for: {kicad_pcb_file}")
        return send_file(
            kicad_pcb_file,
            as_attachment=True,
            download_name=f"{filename}.kicad_pcb",
            mimetype="application/octet-stream"
        )
    else:
        return jsonify({
            "status": "failed",
            "error": "File not found for download."
        }), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)