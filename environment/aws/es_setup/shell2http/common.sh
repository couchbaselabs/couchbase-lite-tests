read_http_body() {
  local len="${HTTP_CONTENT_LENGTH:-}"
  if [[ -n "$len" ]]; then
    head -c "$len"
  else
    cat
  fi
}