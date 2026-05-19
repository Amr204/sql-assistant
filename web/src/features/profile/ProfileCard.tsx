import { Card } from "../../components/ui/Card";
import type { ProfileResponse } from "../../api/types";

interface ProfileCardProps {
  profile: ProfileResponse | null;
  error: string | null;
}

export function ProfileCard({ profile, error }: ProfileCardProps) {
  return (
    <Card>
      <h3 style={{ fontSize: 17 }}>Active Profile</h3>
      {error && (
        <p style={{ color: "var(--color-danger)", fontSize: 14, margin: "8px 0 0" }}>{error}</p>
      )}
      {!profile && !error && (
        <p style={{ color: "var(--color-muted)", fontSize: 14, margin: "8px 0 0" }}>Loading…</p>
      )}
      {profile && (
        <dl
          style={{
            margin: "12px 0 0",
            display: "grid",
            gap: 8,
            fontSize: 14,
          }}
        >
          <div>
            <dt style={{ color: "var(--color-muted)", margin: 0 }}>Profile ID</dt>
            <dd style={{ margin: "4px 0 0" }}>{profile.profile_id}</dd>
          </div>
          <div>
            <dt style={{ color: "var(--color-muted)", margin: 0 }}>Display name</dt>
            <dd style={{ margin: "4px 0 0" }}>{profile.display_name}</dd>
          </div>
          <div>
            <dt style={{ color: "var(--color-muted)", margin: 0 }}>Dialect</dt>
            <dd style={{ margin: "4px 0 0" }}>{profile.dialect}</dd>
          </div>
          <div>
            <dt style={{ color: "var(--color-muted)", margin: 0 }}>Tables</dt>
            <dd style={{ margin: "4px 0 0" }}>{profile.table_count}</dd>
          </div>
          <div>
            <dt style={{ color: "var(--color-muted)", margin: 0 }}>Allowed groups</dt>
            <dd style={{ margin: "4px 0 0" }}>{profile.allowed_groups.join(", ") || "—"}</dd>
          </div>
        </dl>
      )}
    </Card>
  );
}
