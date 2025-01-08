import logging
import os
import requests
from cloudflare import Cloudflare
from datetime import datetime
from zoneinfo import ZoneInfo

# Set up logging with a custom formatter
class RequestFormatter(logging.Formatter):
    def __init__(self):
        super().__init__(fmt='%(asctime)s - %(levelname)s - %(message)s', 
                        datefmt='%Y-%m-%d %H:%M:%S')

    def formatTime(self, record, datefmt=None):
        # Get datetime in the given timezone
        dt = datetime.fromtimestamp(record.created, tz=ZoneInfo(os.getenv('TIMEZONE')))
        if datefmt:
            s = dt.strftime(datefmt)
        else:
            s = dt.strftime('%Y-%m-%d %H:%M:%S')
        return s

# Configure logging
logger = logging.getLogger('cloudflare_updater')
logger.setLevel(logging.INFO)

# Clear existing handlers
logger.handlers = []

# Ensure logs directory exists
os.makedirs('./logs', exist_ok=True)

# File handler
log_file = '/app/logs/cloudflare_updater.log'
file_handler = logging.FileHandler(log_file, mode='w')  # 'w' mode clears the file on start
file_handler.setFormatter(RequestFormatter())
logger.addHandler(file_handler)

def get_public_ip(request_id):
    """Fetch the public IP address of the machine."""
    ip_services = [
        'https://1.1.1.1/cdn-cgi/trace',  # Cloudflare
        'https://checkip.amazonaws.com',   # Amazon AWS
    ]
    
    timeout = 5  # seconds
    
    for service in ip_services:
        try:
            logger.info(f"Attempting to fetch IP from {service}", extra={'request_id': request_id})
            response = requests.get(service, timeout=timeout)
            response.raise_for_status()
            
            if service == 'https://1.1.1.1/cdn-cgi/trace':
                for line in response.text.splitlines():
                    if line.startswith('ip='):
                        ip = line.split('=')[1].strip()
                        logger.info(f"Successfully retrieved IP (Cloudflare): {ip}", 
                                  extra={'request_id': request_id})
                        return ip
            else:
                ip = response.text.strip()
                logger.info(f"Successfully retrieved IP (AWS): {ip}", 
                          extra={'request_id': request_id})
                return ip
            
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch IP from {service}: {str(e)}", 
                         extra={'request_id': request_id})
            continue
    
    error_msg = "Failed to fetch public IP from all services"
    logger.error(error_msg, extra={'request_id': request_id})
    raise Exception(error_msg)

def update_cloudflare_record(zone_id, record_id, public_ip, client, request_id):
    """Update the Cloudflare A record to the current public IP."""
    try:
        logger.info(
            f"Updating DNS record - Zone ID: {zone_id}, Record ID: {record_id}, New IP: {public_ip}", 
            extra={'request_id': request_id}
        )
        
        record = client.dns.records.edit(
            zone_id=zone_id,
            dns_record_id=record_id,
            type='A',
            name=os.getenv('CLOUDFLARE_RECORD_NAME'),
            content=public_ip,
            ttl=1,
            proxied=False
        )
        logger.info(f"Successfully updated DNS record: {record}", 
                   extra={'request_id': request_id})
    except Exception as e:
        logger.error(f"Failed to update Cloudflare record: {e}", 
                    extra={'request_id': request_id})
        raise

def main():
    """Main function to check and update the Cloudflare A record."""
    request_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    logger.info("=" * 80)
    logger.info("Starting new DNS update run")
    logger.info("=" * 80)
    
    email = os.getenv('CLOUDFLARE_EMAIL')
    api_key = os.getenv('CLOUDFLARE_API_KEY')
    zone_id = os.getenv('CLOUDFLARE_ZONE_ID')
    record_name = os.getenv('CLOUDFLARE_RECORD_NAME')

    logger.info(f"Configuration loaded - Email: {email}, Zone ID: {zone_id}, Record Name: {record_name}")

    if not all([email, api_key, zone_id]):
        logger.error("Missing required environment variables")
        return

    try:
        logger.info("Initializing Cloudflare client")
        client = Cloudflare(api_email=email, api_key=api_key)

        logger.info(f"Fetching DNS records for zone {zone_id}")
        records = client.dns.records.list(zone_id=zone_id)
        logger.info(f"Found {len(records.result)} DNS records")
        
        target_record = None
        for record in records.result:
            record_dict = record.model_dump()
            if record_dict.get('type') == 'A' and record_dict.get('name') == record_name:
                target_record = record_dict
                logger.info(f"Found matching A record: {record_dict.get('name')}")
                break
        
        if not target_record:
            logger.error(f"No A record found for {record_name}")
            return
            
        record_id = target_record['id']
        record_ip = target_record['content']
        
        logger.info(f"Current record - ID: {record_id}, IP: {record_ip}")

        public_ip = get_public_ip(request_id)

        if record_ip != public_ip:
            logger.info(f"IP mismatch detected. Current: {record_ip}, New: {public_ip}")
            update_cloudflare_record(zone_id, record_id, public_ip, client, request_id)
        else:
            logger.info(f"No update needed. IP matches: {public_ip}")

    except Exception as e:
        logger.error(f"Process failed: {e}")

    logger.info("DNS update process completed")
    logger.info("=" * 80 + "\n")

if __name__ == "__main__":
    main()