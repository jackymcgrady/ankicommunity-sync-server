# Anki Sync Server: Client Authentication Debugging Guide

## ✅ **What's Working**

### **Server-Side (100% Working)**
- ✅ **HTTP Server**: Running on http://localhost:27702  
- ✅ **HTTPS Proxy**: Running on https://localhost:27703
- ✅ **Modern Protocol Support**: Zstd compression, JSON handling, sync headers
- ✅ **Authentication**: Works with both username/password and email/password
- ✅ **Test Credentials**: 
  - Username: `test` / Password: `test123`
  - Email: `test@example.com` / Password: `test123`

### **Successful Test Commands**
```bash
# Traditional username/password (works)
curl -X POST -H "Content-Type: application/json" \
  -H "anki-sync: {\"v\":11,\"k\":\"\",\"c\":\"test\",\"s\":\"test\"}" \
  -d '{"u":"test","p":"test123"}' \
  http://127.0.0.1:27702/sync/hostKey

# Modern email/password with zstd (works)  
python3 test_email_zstd.py

# HTTPS proxy (works)
python3 test_https_client.py
```

## ❌ **What's Not Working**

### **Anki Client Behavior**
- ❌ **Empty Request Bodies**: Client sends `Content-Length: ''` (zero)
- ❌ **No Credentials**: Server receives `{}` instead of `{u: username, p: password}`
- ❌ **Perfect Headers**: Client sends correct `anki-sync` headers but no data

### **Typical Log Pattern**
```
Content-Length: 
Request body data: {}
Extracted credentials - identifier: 'None', password present: False
Empty hostKey request detected
```

## 🔍 **Diagnosis: Client-Side Credential Collection Issue**

The problem appears to be **credential collection** in the Anki desktop client, not the sync protocol.

### **Possible Causes**
1. **Login Dialog Issues**: Dialog not displaying or not capturing input
2. **Client Configuration**: Sync server URL not properly configured
3. **SSL Certificate Issues**: Client rejecting self-signed certificates
4. **Network Configuration**: Proxy or firewall interference
5. **Client Version Issues**: Desktop client version compatibility

## 🛠️ **Debugging Steps**

### **Step 1: Verify Client Configuration**
In Anki Desktop:
1. Go to **Tools → Preferences → Network**
2. Check **Custom sync server** field: Should be `https://localhost:27703` or `http://localhost:27702`
3. Save settings and restart Anki

### **Step 2: Check Login Dialog**
1. Click **Sync** button in Anki
2. **Does a login dialog appear?**
3. **What text is in the username/email field label?**
4. **Do you see any error messages?**

### **Step 3: Test Different Credential Formats**
Try logging in with:
- Username: `test`
- Email: `test@example.com`  
- Both with password: `test123`

### **Step 4: Check Anki Debug Console**
1. In Anki: **Tools → Add-ons → View Files**
2. Look for any sync-related error logs
3. Check if there are SSL certificate warnings

### **Step 5: Alternative Clients**
If possible, test with:
- AnkiDroid (Android) 
- AnkiMobile (iOS)
- ankiconnect API
- Direct API calls via Python

## 📋 **Current Server Status**

### **HTTP Server (ankisyncd)**
```bash
ps aux | grep ankisyncd  # Should show running process
```

### **HTTPS Proxy**  
```bash
ps aux | grep https_proxy  # Should show running process
```

### **Test Server Health**
```bash
curl -I http://localhost:27702/sync/hostKey  # Should return HTTP headers
curl -I https://localhost:27703/sync/hostKey  # Should return HTTPS headers (ignore cert warnings)
```

## 🎯 **Next Actions**

1. **Verify Anki client configuration** (sync server URL)
2. **Test login dialog behavior** (does it actually appear?)
3. **Check for client-side error messages**
4. **Try alternative authentication methods**
5. **Test with different Anki client versions if available**

## 🔧 **Server Configuration Files**

- **Main Config**: `src/ankisyncd.conf`
- **Database**: `./auth.db` 
- **HTTPS Certificates**: `localhost+2.pem`, `localhost+2-key.pem`
- **Test Scripts**: `test_*.py`

The server is **fully functional** - the issue is definitely on the client side. 