-- Owner = the member who created the family. The column stays nullable: the family row is
-- inserted before its first member, so the FK cannot be satisfied (or NOT NULL enforced) at that
-- point; create_family sets it in the same transaction. A family without an adult keeps NULL.
ALTER TABLE families
    ADD COLUMN owner_member_id uuid REFERENCES members (id) ON DELETE SET NULL;

UPDATE families f
SET owner_member_id = (
    SELECT m.id FROM members m
    WHERE m.family_id = f.id AND m.role = 'adult'
    ORDER BY m.created_at, m.id
    LIMIT 1
);
