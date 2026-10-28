ALTER TABLE shiliu.model_dispatch_receipts
    DROP CONSTRAINT model_dispatch_receipts_status_check;
ALTER TABLE shiliu.model_dispatch_receipts
    ADD CONSTRAINT dispatch_receipt_status_check
    CHECK (status IN ('reserved','settled','unknown','released'));
