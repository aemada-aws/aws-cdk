#!/usr/bin/env python3
"""
EKS V1 to V2 Migration Helper Script

This script automates the migration process by:
1. Fetching physical IDs from CloudFormation stack resources
2. Generating resource mapping JSON for cdk import
3. Providing migration guidance

Usage:
    python migration-helper.py --stack-name MyStack --region us-east-1
"""

import argparse
import boto3
import json
import sys
from typing import Dict, Any, Optional

class EKSMigrationHelper:
    def __init__(self, stack_name: str, region: str, profile: Optional[str] = None):
        self.stack_name = stack_name
        self.region = region
        
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        self.cf_client = session.client('cloudformation', region_name=region)
        self.eks_client = session.client('eks', region_name=region)
        
    def get_stack_resources(self) -> Dict[str, Any]:
        """Fetch all resources from the CloudFormation stack"""
        try:
            paginator = self.cf_client.get_paginator('list_stack_resources')
            resources = {}
            
            for page in paginator.paginate(StackName=self.stack_name):
                for resource in page['StackResourceSummaries']:
                    resources[resource['LogicalResourceId']] = {
                        'Type': resource['ResourceType'],
                        'PhysicalResourceId': resource['PhysicalResourceId'],
                        'Status': resource['ResourceStatus']
                    }
            
            return resources
        except Exception as e:
            print(f"Error fetching stack resources: {e}")
            sys.exit(1)
    
    def generate_resource_mapping(self, resources: Dict[str, Any]) -> Dict[str, Any]:
        """Generate resource mapping for cdk import"""
        mapping = {}
        
        for logical_id, resource in resources.items():
            resource_type = resource['Type']
            physical_id = resource['PhysicalResourceId']
            
            if resource_type == 'AWS::IAM::Role':
                # Extract role name from ARN or use physical ID directly
                role_name = physical_id.split('/')[-1] if '/' in physical_id else physical_id
                mapping[logical_id] = {"RoleName": role_name}
                
            elif resource_type == 'AWS::EC2::SecurityGroup':
                mapping[logical_id] = {"Id": physical_id}
                
            elif resource_type == 'AWS::EKS::Cluster':
                mapping[logical_id] = {"Name": physical_id}
                
            elif resource_type == 'AWS::EKS::Nodegroup':
                mapping[logical_id] = {"Id": physical_id}
                
            elif resource_type == 'AWS::EKS::AccessEntry':
                # For access entries, we need cluster name and principal ARN
                cluster_name = self._extract_cluster_name_from_access_entry(physical_id)
                principal_arn = self._get_access_entry_principal(physical_id, cluster_name)
                if cluster_name and principal_arn:
                    mapping[logical_id] = {
                        "PrincipalArn": principal_arn,
                        "ClusterName": cluster_name
                    }
                    
            elif resource_type == 'AWS::CloudFormation::WaitConditionHandle':
                # For kubectl ready barriers and similar resources
                mapping[logical_id] = {"Name": physical_id}
        
        return mapping
    
    def _extract_cluster_name_from_access_entry(self, access_entry_id: str) -> Optional[str]:
        """Extract cluster name from access entry ID format: cluster-name/principal-arn"""
        try:
            return access_entry_id.split('/')[0]
        except:
            return None
    
    def _get_access_entry_principal(self, access_entry_id: str, cluster_name: str) -> Optional[str]:
        """Get principal ARN for access entry"""
        try:
            # Access entry ID format: cluster-name/principal-arn
            parts = access_entry_id.split('/', 1)
            if len(parts) == 2:
                return parts[1]
        except:
            pass
        return None
    
    def save_mapping_file(self, mapping: Dict[str, Any], filename: str = "eks_v2_mapping.json"):
        """Save resource mapping to JSON file"""
        try:
            with open(filename, 'w') as f:
                json.dump(mapping, f, indent=2)
            print(f"Resource mapping saved to {filename}")
        except Exception as e:
            print(f"Error saving mapping file: {e}")
            sys.exit(1)
    
    def print_migration_summary(self, resources: Dict[str, Any]):
        """Print summary of resources found"""
        print(f"\n=== Migration Summary for Stack: {self.stack_name} ===")
        
        resource_counts = {}
        for resource in resources.values():
            resource_type = resource['Type']
            resource_counts[resource_type] = resource_counts.get(resource_type, 0) + 1
        
        print("\nResources found:")
        for resource_type, count in sorted(resource_counts.items()):
            print(f"  {resource_type}: {count}")
        
        print(f"\nTotal resources: {len(resources)}")
    
    def run_migration_helper(self, output_file: str = "eks_v2_mapping.json"):
        """Main migration helper workflow"""
        print(f"Fetching resources from CloudFormation stack: {self.stack_name}")
        
        resources = self.get_stack_resources()
        self.print_migration_summary(resources)
        
        mapping = self.generate_resource_mapping(resources)
        
        if mapping:
            self.save_mapping_file(mapping, output_file)
            print(f"\n=== Next Steps ===")
            print(f"1. Review the generated mapping file: {output_file}")
            print(f"2. Run: cdk import --resource-mapping {output_file}")
            print("3. You may need to use --force flag for VPC imports")
        else:
            print("No importable resources found in the stack")

def main():
    parser = argparse.ArgumentParser(description='EKS V1 to V2 Migration Helper')
    parser.add_argument('--stack-name', required=True, help='CloudFormation stack name')
    parser.add_argument('--region', required=True, help='AWS region')
    parser.add_argument('--profile', help='AWS profile to use')
    parser.add_argument('--output', default='eks_v2_mapping.json', help='Output mapping file')
    
    args = parser.parse_args()
    
    helper = EKSMigrationHelper(args.stack_name, args.region, args.profile)
    helper.run_migration_helper(args.output)

if __name__ == '__main__':
    main()