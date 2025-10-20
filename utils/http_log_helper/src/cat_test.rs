use std::collections::BTreeMap;
use std::fs;

use walkdir::WalkDir;
use crate::utils;

pub fn run(in_path: &str, out_file: Option<String>, desired_test_name: &str) {
    let mut collected: BTreeMap<String, String> = BTreeMap::new();
    let _ = out_file;
     for entry in WalkDir::new(in_path) {
        match entry {
            Ok(e) => {
                if e.file_type().is_file() {
                    if let Some(os_name) = e.file_name().to_str() {
                        let test_name: Option<&str> = utils::extract_test_name(os_name);
                        if let Some(name) = test_name {
                            if name == desired_test_name {
                                let file_content = fs::read_to_string(e.path());
                                collected.insert(os_name.to_string(), file_content.unwrap());
                            }
                        }
                    }
                }
            }
            Err(e) => eprintln!("Error reading entry: {}", e),
        }
    }

    match out_file {
        Some(file) => {
            let mut output = String::new();
            for (name, content) in collected {
                output.push_str(&format!("Test: {}\nContent:\n{}\n\n", name, content));
            }
            fs::write(&file, output).expect("Unable to write to output file");
            println!("Extracted data written to {}", file);
        }
        None => {
            for (name, content) in collected {
                println!("-- {name} --");
                println!("");
                println!("{}", content);
                println!("");
                println!("-- End of {name} --");
            }
        }
    }
}