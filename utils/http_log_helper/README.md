# HTTP Log Helper

This tool helps pick out specific tests from the (usually large) collection of logs in the http_logs folder, but more importantly this is an easy introduction for me to learn Rust.

## Building

Standard cargo commands `cargo build` and `cargo run` will do the job.

## Options

There are two commands: list-tests and cat-test.  It should be pretty clear what they do.  You can run help on each of them:

```
cargo run -- list-tests --help

Usage: http_log_helper list-tests [OPTIONS] --in-path <IN_PATH>

Options:
  -i, --in-path <IN_PATH>  Path to the input file or directory containing HTTP logs
  -j, --json               Output json instead of table
  -h, --help               Print help
```