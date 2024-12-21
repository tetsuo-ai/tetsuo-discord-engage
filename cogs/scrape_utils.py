import random
from typing import Dict, Any
import asyncio

class ScrapeUtils:
    @staticmethod
    def get_random_headers() -> Dict[str, str]:
        chrome_versions = ['130.0.6723.73', '130.0.6723.69', '129.0.6666.66']
        platforms = [
            ('Windows NT 10.0; Win64; x64', 'Windows'),
            ('Macintosh; Intel Mac OS X 10_15_7', 'Mac'),
            ('X11; Linux x86_64', 'Linux')
        ]
        
        platform, os_type = random.choice(platforms)
        chrome_version = random.choice(chrome_versions)
        
        headers = {
            'User-Agent': f'Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version} Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }
        
        # Randomly include or exclude certain headers
        if random.random() > 0.3:
            headers['Sec-CH-UA'] = f'"Not_A Brand";v="8", "Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}"'
        if random.random() > 0.3:
            headers['Sec-CH-UA-Mobile'] = '?0'
        if random.random() > 0.3:
            headers['Sec-CH-UA-Platform'] = f'"{os_type}"'
            
        return headers

    @staticmethod
    async def random_delay(base_seconds: float = 30) -> None:
        """Add human-like jitter to delays"""
        jitter = random.uniform(-0.2 * base_seconds, 0.2 * base_seconds)
        await asyncio.sleep(base_seconds + jitter)