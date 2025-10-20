use crate::utils;

use walkdir::WalkDir;
use std::collections::HashMap;
use indicatif::ProgressBar;
use tabled::{settings::{Margin, Panel, Style}, Table, Tabled};

#[derive(Tabled)]
#[tabled(rename_all = "Upper Title Case")]
struct TestRow { test_name: String, found_count: u32 }

pub fn run(in_path: &str) {
    let mut seen: HashMap<String, u32> = HashMap::new();

    let total = WalkDir::new(in_path)
        .into_iter()
        .filter_map(Result::ok)
        .count();

    let pb = ProgressBar::new(total as u64);
    pb.set_message("Scanning for tests...");

    for entry in WalkDir::new(in_path) {
        match entry {
            Ok(e) => {
                if e.file_type().is_file() {
                    if let Some(os_name) = e.file_name().to_str() {
                        let test_name: Option<&str> = utils::extract_test_name(os_name);
                        if let Some(name) = test_name {
                            pb.inc(1);
                            if name == "no-test" {
                                continue; // Skip files with "no_test" in their name
                            }

                            if seen.contains_key(name) {
                                let count = seen.get_mut(name).unwrap();
                                *count += 1;
                            } else {
                                seen.insert(name.to_string(), 1);
                            }
                        }
                    }
                }
            }
            Err(e) => eprintln!("Error reading entry: {}", e),
        }
    }

    pb.finish_with_message("Done!");
    let rows: Vec<TestRow> = seen.into_iter()
        .map(|(name, count)| TestRow { test_name: name, found_count: count})
        .collect();

    let found_count = rows.len();
    println!("{}", Table::new(rows)
        .with(Style::psql())
        .with(Panel::header(format!("Found {} tests:", found_count)))
        .with(Margin::new(0, 0, 2, 0)));

}