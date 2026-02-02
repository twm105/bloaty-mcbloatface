#!/bin/bash
curl -X POST 'http://localhost:8000/diagnosis/analyze' \
  -H 'Content-Type: application/json' \
  -d '{"web_search_enabled":false,"min_meals":1,"min_symptom_occurrences":1}'
