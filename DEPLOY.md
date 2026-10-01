# Deploy CVision lên Streamlit Community Cloud

## 1. Đưa source code lên GitHub
Tạo một repository mới trên GitHub, ví dụ `cvision`.

Upload toàn bộ file/thư mục trong ZIP này vào **root của repository**:
- `app.py`
- `processor.py`
- `matcher.py`
- `cv_checker.py`
- `constants.py`
- `file_reader.py`
- `backend/` (toàn bộ thư mục backend mới)
- `requirements.txt`
- `.streamlit/config.toml`
- các file còn lại

Backend đọc `GEMINI_API_KEY` và `GEMINI_MODEL` từ environment hoặc Streamlit secrets.
Trong phần Secrets của Streamlit Community Cloud, đặt `GEMINI_API_KEY = "your-key"`
và tùy chọn `GEMINI_MODEL = "gemini-2.5-flash"`. Không commit key hoặc đặt key trực tiếp
trong source. Khi không có key, phân tích cơ bản vẫn hoạt động. Xem `README.md` và
`.env.example` để cấu hình backend.

Không upload nguyên file ZIP vào repo rồi để đó; Streamlit cần nhìn thấy `app.py` và `requirements.txt`.

## 2. Deploy
1. Mở Streamlit Community Cloud.
2. Đăng nhập bằng GitHub.
3. Chọn **Create app / New app**.
4. Chọn repository `cvision`.
5. Branch: `main`.
6. Main file path: `app.py`.
7. Deploy.

Sau khi build xong, Streamlit cung cấp URL public dạng:
`https://<ten-app>.streamlit.app`

## 3. Web public làm được gì?
- Upload CV PDF / DOCX / TXT.
- Upload JD PDF / DOCX / TXT hoặc paste JD.
- Xem text được trích xuất trước khi phân tích.
- Analyze CV ↔ JD.
- Xem Match Score, required criteria, keyword gaps, CV quality.
- Download text analysis report.

## Lưu ý
Match Score là điểm alignment theo rule của CVision, không phải điểm ATS chính thức hoặc xác suất được tuyển.
