#!/usr/bin/env bash
# Generates the RSA keypair Auth Service uses to sign JWTs.
# Public key gets distributed to every other service via k8s secret;
# private key stays mounted only in Auth Service pods.
set -euo pipefail
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
echo "Keys written to ./keys/private.pem and ./keys/public.pem"
