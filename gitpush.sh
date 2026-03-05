#!/bin/bash
# Usage: ./gitpush.sh "Your commit message"

git add .
git commit -m "$1"
git push origin main
