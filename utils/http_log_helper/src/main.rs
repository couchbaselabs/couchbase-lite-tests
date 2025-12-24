mod list_tests;
mod cat_test;
mod utils;

use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(author, version, about)]
struct Cli {
    #[command(subcommand)]
    command: Commands
}

#[derive(Subcommand)]
enum Commands {
    ListTests {
        #[arg(short, long, help = "Path to the input file or directory containing HTTP logs")]
        in_path: String,

        #[arg(short, long, help = "Output json instead of table")]
        json: bool
    },
    CatTest {
        #[arg(short, long, help = "Path to the input file or directory containing HTTP logs")]
        in_path: String,

        #[arg(short, long, help = "Path to the output file where extracted data will be saved")]
        out_file: Option<String>,

        #[arg(short, long, help = "Name of the test to extract")]
        test_name: String,
    }
}

fn main() {
    let cli: Cli = Cli::parse();


    match cli.command {
        Commands::ListTests { in_path, json } => {
            list_tests::run(&in_path, json);
        }
        Commands::CatTest { in_path, out_file, test_name } => {
            cat_test::run(&in_path, out_file, &test_name);
        }
    }
}