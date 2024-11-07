import UIKit

class ViewController: UIViewController {
    
    @IBOutlet weak var ipLabel: UILabel!
    
    override func viewDidLoad() {
        super.viewDidLoad()
        ipLabel.text = IPAddress.shared.address
    }
}
