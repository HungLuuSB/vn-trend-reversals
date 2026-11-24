#!/bin/sh
# Start a single-node SeaweedFS (master + volume + filer + S3 gateway).
# The S3 identity is generated from env vars so no credentials live in git.
set -eu

: "${S3_ACCESS_KEY:?S3_ACCESS_KEY not set}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY not set}"

mkdir -p /data/etc
umask 077
cat > /data/etc/s3.json <<EOF
{
  "identities": [
    {
      "name": "vnbank",
      "credentials": [
        { "accessKey": "${S3_ACCESS_KEY}", "secretKey": "${S3_SECRET_KEY}" }
      ],
      "actions": ["Admin", "Read", "List", "Tagging", "Write"]
    }
  ]
}
EOF

# volumeSizeLimitMB keeps the pre-allocated volume files small on a laptop disk.
exec weed server \
  -dir=/data \
  -ip.bind=0.0.0.0 \
  -master.volumeSizeLimitMB=1024 \
  -volume.max=0 \
  -s3 \
  -s3.port=8333 \
  -s3.config=/data/etc/s3.json
