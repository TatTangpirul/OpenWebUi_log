#!/bin/bash
kubectl get pods -n "$1" -o jsonpath='{.items[*].metadata.name}{"\n"}' | tr ' ' '\n'