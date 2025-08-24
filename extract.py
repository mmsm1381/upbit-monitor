import re
from typing import Dict, List, Optional


class MarketSupportExtractor:
    def __init__(self):
        """Initialize the market support text extractor"""
        # Pattern to match the market support announcement format
        self.pattern = r'Market Support for\s+(.+?)\(([A-Z0-9]+)\)\s*\((.+?)\s+Market\)'

    def extract_market_info(self, text: str) -> Optional[Dict[str, str]]:
        """
        Extract symbol, name, and quote currencies from market support text

        Args:
            text: Input text containing market support announcement

        Returns:
            Dictionary with symbol, name, and quote currencies or None if no match
        """
        # Clean the text - remove extra whitespace and normalize
        cleaned_text = ' '.join(text.split())

        # Search for the pattern
        match = re.search(self.pattern, cleaned_text)

        if not match:
            return None

        # Extract the matched groups
        name = match.group(1).strip()
        symbol = match.group(2).strip()
        markets = match.group(3).strip()

        # Parse the quote currencies
        quote_currencies = self.parse_quote_currencies(markets)

        return {
            'symbol': symbol,
            'name': name,
            'quote': quote_currencies
        }

    def parse_quote_currencies(self, markets_text: str) -> List[str]:
        """
        Parse quote currencies from the markets text

        Args:
            markets_text: Text containing market information like "KRW, BTC, USDT"

        Returns:
            List of quote currencies
        """
        # Split by comma and clean up
        currencies = [currency.strip() for currency in markets_text.split(',')]

        # Remove "Market" suffix if present
        cleaned_currencies = []
        for currency in currencies:
            # Remove "Market" word and any extra whitespace
            cleaned = re.sub(r'\s*Market\s*', '', currency, flags=re.IGNORECASE).strip()
            if cleaned:
                cleaned_currencies.append(cleaned)

        return cleaned_currencies

    def extract_multiple(self, texts: List[str]) -> List[Dict[str, str]]:
        """
        Extract market info from multiple texts

        Args:
            texts: List of text strings to process

        Returns:
            List of extracted market information dictionaries
        """
        results = []
        for text in texts:
            result = self.extract_market_info(text)
            if result:
                results.append(result)

        return results


def test_extractor():
    """Test function with various text formats"""
    extractor = MarketSupportExtractor()

    # Test cases
    test_texts = [
        "Market Support for Omni Network(OMNI)(KRW, BTC, USDT Market)",
        "Market Support for Bitcoin Cash(BCH)(KRW Market)",
        "Market Support for Ethereum Classic(ETC)(KRW, BTC, USDT Market)",
        "Market Support for Chainlink(LINK)(KRW, BTC Market)",
        "Market Support for Polygon(MATIC)(USDT Market)",
        # Additional variations
        "Market Support for Uniswap (UNI) (KRW, BTC, USDT Market)",
        "Market Support for Solana(SOL)(KRW,BTC,USDT Market)",
    ]

    print("=" * 60)
    print("MARKET SUPPORT TEXT EXTRACTOR - TEST RESULTS")
    print("=" * 60)

    for i, text in enumerate(test_texts, 1):
        print(f"\nTest {i}:")
        print(f"Input:  {text}")

        result = extractor.extract_market_info(text)

        if result:
            print(f"Symbol: {result['symbol']}")
            print(f"Name:   {result['name']}")
            print(f"Quote:  {', '.join(result['quote'])}")
        else:
            print("No match found")

        print("-" * 40)


def extract_from_text(input_text: str) -> Dict[str, str]:
    """
    Simple function to extract market info from a single text

    Args:
        input_text: The text to extract information from

    Returns:
        Dictionary with symbol, name, and quote currencies
    """
    extractor = MarketSupportExtractor()
    result = extractor.extract_market_info(input_text)

    if result:
        return result
    else:
        raise Exception("No match found")

if __name__ == '__main__':
    extractor = extract_from_text("Market Support for API3(API3) (KRW, USDT Market)")
    print(extractor)
    # test_extractor()