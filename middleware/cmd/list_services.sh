#!/bin/bash
kubectl get svc -n "$1" -o jsonpath='{.items[*].metadata.name}{"\n"}' | tr ' ' '\n'