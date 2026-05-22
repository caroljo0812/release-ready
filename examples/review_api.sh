curl -s http://localhost:8080/review/diff \
  -H 'Content-Type: application/json' \
  -d "{
    \"diff\": $(cat examples/simple.diff | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))"),
    \"specialists\": [\"changelog\", \"compatibility\"]
  }" | python3 -m json.tool