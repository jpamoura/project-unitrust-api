# API Examples - Unitrust API

## CSV Comparison Endpoints

### POST /compare/preview

**Description**: Upload a CSV file for comparison preview and get a confirmation token.

**Request**:
```bash
curl -X POST "http://localhost:8000/compare/preview" \
  -F "csv_file=@example.csv" \
  -F "custom_data={\"user_id\": 123, \"session\": \"abc123\"}" \
  -F "forward_url=https://your-webhook.com/csv-preview" \
  -F "bearer=your-bearer-token"
```

**Response** (Updated):
```json
{
  "ok": true,
  "token": "abc123def456ghi789",
  "message": "File uploaded successfully. Use the token to confirm the upload."
}
```

**Previous Response** (Old):
```json
{
  "ok": true
}
```

### POST /compare/confirm

**Description**: Confirm the CSV upload using the token received from preview.

**Request**:
```json
{
  "token": "abc123def456ghi789"
}
```

**Response**:
```json
{
  "ok": true,
  "message": "CSV upload confirmed and processed successfully"
}
```

## Workflow Example

1. **Upload CSV for preview**:
   ```bash
   curl -X POST "http://localhost:8000/compare/preview" \
     -F "csv_file=@data.csv" \
     -F "custom_data={\"user\": \"john_doe\"}"
   ```

2. **Response with token**:
   ```json
   {
     "ok": true,
     "token": "xyz789abc123def456",
     "message": "File uploaded successfully. Use the token to confirm the upload."
   }
   ```

3. **Confirm the upload**:
   ```bash
   curl -X POST "http://localhost:8000/compare/confirm" \
     -H "Content-Type: application/json" \
     -d '{"token": "xyz789abc123def456"}'
   ```

4. **Confirmation response**:
   ```json
   {
     "ok": true,
     "message": "CSV upload confirmed and processed successfully"
   }
   ```

## Benefits of Token Return

- **Immediate Feedback**: Client knows the upload was successful
- **Token for Confirmation**: Client can use the token to confirm the upload
- **Better UX**: Clear workflow with confirmation step
- **Error Handling**: Client can retry confirmation if needed
- **Audit Trail**: Token can be used for tracking and debugging
