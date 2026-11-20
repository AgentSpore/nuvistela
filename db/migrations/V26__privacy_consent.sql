-- Proof that the adult who created the family accepted the privacy policy: when and which text.
-- Nullable: families created before the policy existed have no consent on record.
ALTER TABLE families
    ADD COLUMN privacy_consent_at timestamptz,
    ADD COLUMN privacy_policy_version text;
