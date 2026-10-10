import os
import requests

BASE_URL = "https://raw.githubusercontent.com/defcom17/NSL_KDD/master"

FILES = [
    "KDDTrain+.txt",
    "KDDTest+.txt",
    "KDDTrain+_20Percent.txt",
    "KDDTest-21.txt",
]

DOWNLOAD_DIR = "rawdata/NSL-KDD"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def download_file(filename):
    url = f"{BASE_URL}/{filename}"
    save_path = os.path.join(DOWNLOAD_DIR, filename)

    print(f"Downloading {filename}...")

    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(save_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file.write(chunk)

    print(f"Saved: {save_path}")


for filename in FILES:
    download_file(filename)

print("\nNSL-KDD dataset downloaded successfully.")