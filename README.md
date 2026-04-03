# 🚀 DineFlow Backend

A production-grade **microservices backend** secured with **JWT at API Gateway level (NGINX + OpenResty)** using **RS256**, built with Django, Docker, and Redis.

---

## 🧠 Architecture Overview

This backend follows a **Gateway Authentication Pattern**:

```
Client / Swagger UI
        ↓ (Bearer Token)
NGINX (OpenResty + Lua)
  ├── JWT Verification (RS256)
  ├── Token Expiry Enforcement
  ├── Header Injection (Trusted)
  ↓
Microservices (Django)
```

### Key Idea

* **Authentication happens ONLY at the gateway**
* Microservices **never verify JWT tokens**
* Services trust headers injected by the gateway

---

## 🧩 Services

| Service           | Responsibility                               |
| ----------------- | -------------------------------------------- |
| **Auth Service**  | User login, token issuance (RS256 JWT)       |
| **Menu Service**  | Categories, dishes, reviews                  |
| **NGINX Gateway** | JWT verification, routing, security          |
| **Redis**         | Caching (JWT public key, future rate limits) |
| **PostgreSQL**    | Databases per service                        |

---

## 🔐 Authentication & Security

### JWT Strategy

* Algorithm: **RS256**
* Private key: **Auth Service only**
* Public key: **NGINX Gateway**

### Where JWT Is Verified

✅ **Only in NGINX**

```lua
jwt:verify(public_key, token)
```

### What Happens After Verification

NGINX injects trusted headers:

```
X-User-Id
X-User-Role
X-User-Email
```

Microservices **do not read Authorization headers**.

---

## 🌐 API Gateway (NGINX)

### Responsibilities

* JWT verification (RS256)
* Token expiry enforcement
* Role-based access control (ready)
* Route-based service proxying

### Protected Routes

```
/api/menu/**   → JWT required
```

### Public Routes

```
/api/auth/**
/api/*/health/
/api/*/swagger/
```

---

## 📘 Swagger / API Documentation

### Important Truth

> Swagger **does NOT authenticate users**

It only:

* Collects Bearer token
* Adds `Authorization: Bearer <token>` header

### Current Setup

* Auth Swagger: `/api/auth/swagger/`
* Menu Swagger: `/api/menu/swagger/`
* Works via NGINX reverse proxy
* JWT input works correctly

---

## 🩺 Health Checks

Each component exposes health endpoints for monitoring:

| Endpoint            | Purpose             |
| ------------------- | ------------------- |
| `/health`           | Gateway health      |
| `/api/auth/health/` | Auth service health |
| `/api/menu/health/` | Menu service health |

Used for:

* Docker health checks
* Kubernetes readiness/liveness probes

---

## 🐳 Docker Setup

All services run via **Docker Compose**:

```bash
docker compose up --build
```

Includes:

* NGINX (OpenResty)
* Auth Service (Django)
* Menu Service (Django)
* Redis
* PostgreSQL (per service)

---

## 🔥 Key Engineering Decisions

✔ JWT verification at gateway (not services)
✔ RS256 asymmetric encryption
✔ No shared auth logic between services
✔ Swagger works without breaking security
✔ Clean microservice boundaries

This mirrors **real-world enterprise systems**.

---

## 🛣️ What’s Next

* 🔐 Role-Based Access Control (RBAC) at gateway
* 🚦 Rate limiting via Redis
* 📊 Metrics & logging
* ☁️ AWS / Kubernetes deployment

---

## 👨‍💻 Author

**Akshay Bharathan**
Backend Engineer – Microservices & API Gateway Architecture

---

> This repository represents a **production-ready backend foundation**, not a demo project.


Push to the ECR

chmod +x push_to_aws.sh

./push_to_aws.sh       