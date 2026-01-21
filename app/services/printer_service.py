from sqlalchemy.orm import Session
from typing import List, Optional, Dict
import socket
import uuid
from app.models.document import Document
from app.services.s3_service import s3_service
from app.models.printer import Printer

class PrinterService:
    @staticmethod
    def get_printers(db: Session, skip: int = 0, limit: int = 100) -> List[Printer]:
        return db.query(Printer).offset(skip).limit(limit).all()

    @staticmethod
    def create_printer(db: Session, printer_data: Dict) -> Printer:
        printer = Printer(
            id=str(uuid.uuid4()),
            name=printer_data['name'],
            ip_address=printer_data['ip_address'],
            port=printer_data.get('port', 9100),
            protocol=printer_data.get('protocol', 'RAW'),
            description=printer_data.get('description'),
            status=printer_data.get('status', 'ACTIVE')
        )
        db.add(printer)
        db.commit()
        db.refresh(printer)
        return printer

    @staticmethod
    def update_printer(db: Session, printer_id: str, printer_data: Dict) -> Optional[Printer]:
        printer = db.query(Printer).filter(Printer.id == printer_id).first()
        if not printer:
            return None
        
        for key, value in printer_data.items():
            setattr(printer, key, value)
            
        db.commit()
        db.refresh(printer)
        return printer

    @staticmethod
    def delete_printer(db: Session, printer_id: str) -> Optional[str]:
        printer = db.query(Printer).filter(Printer.id == printer_id).first()
        if not printer:
            return None
            
        printer_name = printer.name
        db.delete(printer)
        db.commit()
        return printer_name

    @staticmethod
    def test_connection(ip_address: str, port: int, timeout: int = 3) -> Dict:
        try:
            sock = socket.create_connection((ip_address, port), timeout=timeout)
            sock.close()
            return {"success": True, "message": "Connection successful"}
        except socket.timeout:
            return {"success": False, "message": "Connection timed out"}
        except ConnectionRefusedError:
            return {"success": False, "message": "Connection refused"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @staticmethod
    def _wrap_pjl(content: bytes, copies: int = 1, color_mode: str = "MONO", duplex: bool = False) -> bytes:
        """
        Wraps PDF content in PJL commands to control printer options.
        """
        # Universal Exit Language (UEL) to reset printer
        uel = b"\x1B%-12345X"
        
        # PJL Header
        header = uel + b"@PJL JOB\n"
        
        # Options
        header += f"@PJL SET COPIES={copies}\n".encode()
        
        if duplex:
            header += b"@PJL SET DUPLEX=ON\n"
        else:
             header += b"@PJL SET DUPLEX=OFF\n"
            
        if color_mode == "COLOR":
            header += b"@PJL SET RENDERMODE=COLOR\n"
        else:
            header += b"@PJL SET RENDERMODE=GRAYSCALE\n"
            
        header += b"@PJL ENTER LANGUAGE=PDF\n"
        
        # Footer
        footer = uel + b"@PJL EOJ\n" + uel
        
        return header + content + footer

    @staticmethod
    async def print_document(db: Session, printer_id: str, document_id: int, copies: int = 1, color_mode: str = "MONO", duplex: bool = False) -> bool:
        # 1. Get Printer
        printer = db.query(Printer).filter(Printer.id == printer_id).first()
        if not printer:
            raise Exception("Printer not found")
        
        # 2. Get Document
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise Exception("Document not found")
            
        if not document.s3_key:
             raise Exception("Document content not available (S3 key missing)")

        # 3. Fetch Content
        try:
            # Assuming s3_service is an instance or has static methods
            file_content = await s3_service.download_file(document.s3_key)
        except Exception as e:
            raise Exception(f"Failed to download document: {str(e)}")

        # 4. Wrap in PJL
        final_content = PrinterService._wrap_pjl(file_content, copies, color_mode, duplex)

        # 5. Send to Printer (RAW)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10) # Longer timeout for data transfer
            sock.connect((printer.ip_address, printer.port))
            sock.sendall(final_content)
            sock.close()
            return True
        except Exception as e:
            raise Exception(f"Failed to send data to printer: {str(e)}")

    @staticmethod
    def discover_printers(timeout: int = 3) -> List[Dict]:
        from zeroconf import Zeroconf, ServiceBrowser
        import time

        discovered = []

        class PrinterListener:
            def remove_service(self, zeroconf, type, name):
                pass

            def add_service(self, zeroconf, type, name):
                info = zeroconf.get_service_info(type, name)
                if info:
                    # Clean up name (remove ._ipp._tcp.local. etc)
                    clean_name = name.split('.')[0]
                    
                    # Parse addresses
                    addresses = []
                    for addr in info.addresses:
                        addresses.append(socket.inet_ntoa(addr))
                    
                    ip = addresses[0] if addresses else None
                    if ip:
                        # Default to what we found
                        final_port = info.port
                        final_protocol = "IPP" if "ipp" in type else "LPD"
                        
                        # Optimization: Check if Port 9100 is open (RAW)
                        # Most office printers support RAW 9100 which is more reliable for our "send bytes" approach
                        try:
                            sock = socket.create_connection((ip, 9100), timeout=0.5)
                            sock.close()
                            final_port = 9100
                            final_protocol = "RAW"
                        except (socket.timeout, ConnectionRefusedError):
                            # Fallback to advertised port if 9100 is closed
                            pass

                        discovered.append({
                            "name": clean_name,
                            "ip_address": ip,
                            "port": final_port,
                            "protocol": final_protocol,
                            "description": info.properties.get(b'ty', b'').decode('utf-8') or "Network Printer"
                        })
            
            def update_service(self, zeroconf, type, name):
                pass

        zeroconf = Zeroconf()
        listener = PrinterListener()
        # Browse for common printer services
        browser = ServiceBrowser(zeroconf, ["_ipp._tcp.local.", "_printer._tcp.local."], listener)
        
        time.sleep(timeout)
        
        zeroconf.close()
        # Deduplicate based on IP
        seen_ips = set()
        unique_discovered = []
        for d in discovered:
            if d['ip_address'] not in seen_ips:
                unique_discovered.append(d)
                seen_ips.add(d['ip_address'])
                
        return unique_discovered
