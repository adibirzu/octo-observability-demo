"""Security-sensitive Maven versions for the Java APM image."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


class DependencyVersionsTest(unittest.TestCase):
    def test_embedded_tomcat_version(self):
        root = ET.parse(Path(__file__).with_name("pom.xml")).getroot()
        ns = {"m": "http://maven.apache.org/POM/4.0.0"}
        self.assertEqual(root.findtext("m:properties/m:tomcat.version", namespaces=ns), "10.1.62")
        self.assertEqual(root.findtext("m:parent/m:version", namespaces=ns), "3.5.16")
        self.assertEqual(root.findtext("m:properties/m:jackson-bom.version", namespaces=ns), "2.23.0")


if __name__ == "__main__":
    unittest.main()
