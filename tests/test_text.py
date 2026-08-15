from localdirectory.text import domain, normalise_name, normalise_phone, normalise_postcode


def test_normalisers():
    assert normalise_name("PEARL Carpentry Ltd") == "pearl carpentry"
    assert normalise_postcode("bn72dg") == "BN7 2DG"
    assert normalise_phone("+44 (0)1273 123456").endswith("1273123456")
    assert domain("https://www.example.co.uk/path") == "example.co.uk"
