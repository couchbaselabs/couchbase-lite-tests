pub fn extract_test_name(s: &str) -> Option<&str> {
    let start = s.find('_')? + 1;
    let end = s.rfind('_')?;
    if start < end {
        Some(&s[start..end])
    } else {
        None
    }
}