import { memo } from "react";
import { Card } from "../../components/ui/Card";
import type { ProfileResponse } from "../../api/types";
import { ui } from "../../locale/uiStrings";
import "./ProfileCard.css";

interface ProfileCardProps {
  profile: ProfileResponse | null;
  error: string | null;
}

export const ProfileCard = memo(function ProfileCard({ profile, error }: ProfileCardProps) {
  return (
    <Card>
      <h3 className="section-title">{ui.activeProfile}</h3>
      {error && <p className="profile-error">{error}</p>}
      {!profile && !error && <p className="text-muted">{ui.loading}</p>}
      {profile && (
        <dl className="profile-dl">
          <div>
            <dt>{ui.profileId}</dt>
            <dd>{profile.profile_id}</dd>
          </div>
          <div>
            <dt>{ui.displayName}</dt>
            <dd>{profile.display_name}</dd>
          </div>
          <div>
            <dt>{ui.dialect}</dt>
            <dd>{profile.dialect}</dd>
          </div>
          <div>
            <dt>{ui.tables}</dt>
            <dd>{profile.table_count}</dd>
          </div>
          <div>
            <dt>{ui.allowedGroups}</dt>
            <dd>{profile.allowed_groups.join(", ") || "—"}</dd>
          </div>
        </dl>
      )}
    </Card>
  );
});
