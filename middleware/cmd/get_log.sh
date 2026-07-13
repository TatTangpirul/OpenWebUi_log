minutes="${3:-60}"
kubectl logs "$1" -n "$2" --since="${minutes}m"