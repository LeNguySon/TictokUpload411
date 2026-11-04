# BÁO CÁO PHÂN TÍCH SỰ CỐ & HẬU KIỂM (ECC POST-MORTEM & RCA REPORT)

> **Mã sự cố**: `INC-[YYYYMMDD]-[TÊN_SỰ_CỐ]`  
> **Mức độ nghiêm trọng**: `[S1 - Blocker | S2 - Critical | S3 - Major | S4 - Minor]`  
> **Thời điểm xảy ra**: `[ISO-8601 Timestamp]`  
> **Thời điểm khắc phục**: `[ISO-8601 Timestamp]`  
> **Người chủ trì điều tra**: [Kỹ sư / AI Investigator]

---

## 1. Tóm Tắt Hiện Tượng (Incident Summary)
- **Mô tả ngắn**: [Hiện tượng cụ thể nhìn thấy từ góc độ người dùng hoặc hệ thống]
- **Tác động (Impact)**: [Bao nhiêu phần trăm request bị lỗi? Có thất thoát dữ liệu hay treo hệ thống không?]
- **Thời gian gián đoạn (Downtime / MTTR)**: [Khoảng thời gian từ lúc phát hiện đến khi vá xong]

---

## 2. Dòng Thời Gian Xảy Ra Sự Cố (Timeline)
- `[HH:MM]`: Bắt đầu xuất hiện triệu chứng bất thường (Log lỗi đầu tiên).
- `[HH:MM]`: Hệ thống cảnh báo hoặc người dùng báo cáo lỗi.
- `[HH:MM]`: Tiếp nhận, cô lập môi trường và tạo bản tái hiện tối thiểu (MRE).
- `[HH:MM]`: Tìm ra nguyên nhân gốc rễ (Root Cause Identified).
- `[HH:MM]`: Viết Regression Test (RED) và tiến hành sửa phẫu thuật (GREEN).
- `[HH:MM]`: Chạy Verification Suite và triển khai bản vá thành công.

---

## 3. Phân Tích Nguyên Nhân Gốc Rễ: Kỹ Thuật 5-Whys (Root Cause Analysis)

Đào sâu để tìm ra căn nguyên thực sự, không dừng lại ở triệu chứng bề mặt:
1. **Tại sao 1 (Triệu chứng)**: Hệ thống trả về lỗi HTTP 500 hoặc crash ứng dụng?  
   $\rightarrow$ *Vì:* Hàm `parse_token()` văng ngoại lệ `AttributeError`.
2. **Tại sao 2**: Tại sao lại văng `AttributeError`?  
   $\rightarrow$ *Vì:* Biến `decoded_payload` nhận giá trị `None` thay vì đối tượng từ khóa.
3. **Tại sao 3**: Tại sao `decoded_payload` lại là `None`?  
   $\rightarrow$ *Vì:* Hàm giải mã JWT bỏ qua việc ném ngoại lệ khi chữ ký hết hạn mà trả về `None`.
4. **Tại sao 4**: Tại sao hàm giải mã lại trả về `None` khi hết hạn?  
   $\rightarrow$ *Vì:* Khối `try...except ExpiredSignatureError:` nuốt lỗi âm thầm và `return None`.
5. **Tại sao 5 (Căn nguyên gốc rễ)**: Tại sao lại nuốt lỗi thay vì ném ngoại lệ tường minh?  
   $\rightarrow$ *Vì:* Thiếu quy chuẩn xử lý ngoại lệ đồng nhất (Exception Hierarchy) và thiếu unit test cho trường hợp token hết hạn.

---

## 4. Hành Động Khắc Phục & Phòng Ngừa (Corrective & Preventative Actions)

| Loại Hành Động | Nội Dung Cụ Thể | Người Thực Hiện | Trạng Thái |
| :--- | :--- | :--- | :---: |
| **Surgical Fix** | Loại bỏ `return None`, ném `TokenExpiredException` tường minh | Kỹ sư | `[DONE]` |
| **Regression Test** | Bổ sung test case `test_expired_token_raises_exception` | Kỹ sư | `[DONE]` |
| **Systemic Guard** | Cập nhật linter cấm câu lệnh `except: pass` hoặc silent returns | AI Agent | `[TODO]` |
| **Instinct Retention**| Ghi nhận Bản năng nguyên tử vào bộ nhớ dự án | AI Agent | `[DONE]` |

---

## 5. Bản Năng Đúc Kết (Extracted Atomic Instinct)

```yaml
id: no-silent-auth-failure-return-none
trigger: "khi viết hàm kiểm tra xác thực hoặc giải mã token"
confidence: 0.95
domain: "security"
scope: project
rule: "Tuyệt đối không trả về None khi xác thực thất bại; luôn ném ngoại lệ chuyên biệt (e.g., AuthenticationFailedException) để buộc tầng gọi phải xử lý tường minh."
evidence: "INC-20261029-AUTH-CRASH"
```
