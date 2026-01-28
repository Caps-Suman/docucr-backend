# Role-Based Activity Logs

This document explains the role-based activity log implementation that restricts access to activity logs based on user hierarchy.

## Role Hierarchy

The system follows this role hierarchy (higher level = more access):

1. **SUPER_ADMIN** (Level 4) - Can see all activity logs
2. **ADMIN** (Level 3) - Can see all logs except SUPER_ADMIN users
3. **SUPERVISOR** (Level 2) - Can see their own logs and their subordinates' logs
4. **USER** (Level 1) - Can only see their own logs

## Implementation Details

### Files Modified/Created

1. **`app/services/user_hierarchy_service.py`** - New service for role hierarchy logic
2. **`app/routers/activity_log_router.py`** - Modified to use role-based filtering
3. **`scripts/seed_roles.sql`** - New script to add missing roles

### API Endpoints

#### GET `/api/activity-logs/`
- **Description**: Get activity logs with pagination and filtering
- **Role-based Access**: Automatically filters logs based on user role
- **Parameters**:
  - `page`: Page number (default: 1)
  - `limit`: Items per page (default: 20, max: 100)
  - `action`: Filter by action type
  - `entity_type`: Filter by entity type
  - `user_id`: Filter by specific user (only if accessible)
  - `user_name`: Search by user name (only searches accessible users)
  - `start_date`: Filter by start date
  - `end_date`: Filter by end date

#### GET `/api/activity-logs/accessible-users`
- **Description**: Get list of users whose activity logs are accessible to current user
- **Use Case**: Useful for frontend dropdown filters
- **Returns**: List of UserSummary objects

### Access Control Examples

#### Super Admin
```json
// Can see all users' activity logs
GET /api/activity-logs/ 
// Returns all logs in the system
```

#### Admin
```json
// Can see all logs except super admin logs
GET /api/activity-logs/
// Returns logs from all users except those with SUPER_ADMIN role
```

#### Supervisor
```json
// Can see their own logs + subordinates' logs
GET /api/activity-logs/
// Returns logs from themselves and users they supervise
```

#### Regular User
```json
// Can only see their own logs
GET /api/activity-logs/
// Returns only logs where user_id = current_user.id
```

### Security Features

1. **Permission Check**: Users still need `activity_log:READ` permission
2. **Role-based Filtering**: Automatic filtering based on user hierarchy
3. **Access Validation**: Explicit checks when filtering by specific user_id
4. **Search Scope**: Name searches only return accessible users

### Error Handling

- **403 Forbidden**: When trying to access logs for inaccessible user
- **401 Unauthorized**: When user lacks required permissions

## Database Setup

Run the seed script to add missing roles:

```sql
-- Run this script to add ADMIN, SUPERVISOR, and USER roles
\i scripts/seed_roles.sql
```

## Frontend Integration

### Recommended Usage

1. **User Filter**: Use `/api/activity-logs/accessible-users` to populate user dropdown
2. **Automatic Filtering**: The API automatically handles role-based access
3. **Error Handling**: Handle 403 errors gracefully when user tries to access restricted logs

### Example Frontend Code

```javascript
// Get accessible users for dropdown
const response = await fetch('/api/activity-logs/accessible-users');
const users = await response.json();

// Get activity logs (automatically filtered by role)
const logsResponse = await fetch('/api/activity-logs/?user_id=userId&limit=20');
const logs = await logsResponse.json();
```

## Testing the Implementation

1. **Create test users** with different roles
2. **Set up supervisor relationships** using `user_supervisor` table
3. **Generate activity logs** for different users
4. **Test access** by logging in as different role types

### Supervisor Relationship Setup

```sql
-- Make user2 supervise user3
INSERT INTO docucr.user_supervisor (id, user_id, supervisor_id, created_at, updated_at)
VALUES (gen_random_uuid(), 'user3_id', 'user2_id', NOW(), NOW());
```

## Future Enhancements

1. **Client-based filtering**: Filter logs by client for client managers
2. **Time-based restrictions**: Limit access to recent logs for certain roles
3. **Audit trail**: Log when users access restricted activity logs
4. **Role customization**: Allow configurable role hierarchies
