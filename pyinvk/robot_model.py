import casadi as cs

# https://pypi.org/project/urdf-parser-py
from urdf_parser_py.urdf import URDF

from .spatialmath import *

class RobotModel:

    def __init__(self, urdf_filename):
        self._urdf = URDF.from_xml_file(urdf_filename)

    @property
    def actuated_joint_names(self):
        """Names of actuated joints"""
        return [jnt.name for jnt in self._urdf.joints if jnt.type != 'fixed']

    @property
    def lower_actuated_joint_limits(self):
        """Lower position limits for actuated joints"""
        return [jnt.limit.lower for jnt in self.robot.joints if jnt.type != 'fixed']

    @property
    def upper_actuated_joint_limits(self):
        """Upper position limits for actuated joints"""
        return [jnt.limit.upper for jnt in self.robot.joints if jnt.type != 'fixed']

    @property
    def ndof(self):
        """Number of Degrees Of Freedom"""
        return len(self.actuated_joint_names)

    @staticmethod
    def get_joint_origin(joint):
        """Get the origin for the joint"""
        xyz, rpy = cs.DM.zeros(3), cs.DM.zeros(3)
        if joint.origin is not None:
            xyz, rpy = cs.DM(joint.origin.xyz), cs.DM(joint.origin.rpy)
        return xyz, rpy

    @staticmethod
    def get_joint_axis(joint):
        """Get the axis of joint, the axis is normalized for revolute/continuous joints"""
        axis = cs.DM(joint.axis) if joint.axis is not None else cs.DM([1., 0., 0.])
        if joint.type in {'revolute', 'continuous'}:
            axis = unit(axis)
        return axis

    @vectorize_args
    def get_global_link_transform(self, link_name, q):
        """Get the link transform in the global frame for a given joint state q"""

        assert link_name in self._urdf.link_map.keys(), "given link_name does not appear in URDF"

        T = I4()
        if link_name == self._urdf.get_root(): return T

        for joint in self._urdf.joints:

            xyz, rpy = self.get_joint_origin(joint)

            if joint.type == 'fixed':
                T  = T @ rt2tr(rpy2r(rpy), xyz)
                continue

            joint_index = self.actuated_joint_names.index(joint.name)
            qi = q[joint_index]

            if joint.type in {'revolute', 'continuous'}:
                T = T @ rt2tr(rpy2r(rpy), xyz)
                T = T @ r2t(angvec2r(qi, self.get_joint_axis(joint)))

            else:
                raise NotImplementedError(f"{joint.type} joints are currently not supported")

            if joint.child == link_name:
                break

        return T

    def get_global_link_position(self, link_name, q):
        """Get the link position in the global frame for a given joint state q"""
        return transl(self.get_global_link_transform(link_name, q))

    @vectorize_args
    def get_global_link_quaternion(self, link_name, q):
        """Get the link orientation as a quaternion in the global frame for a given joint state q"""

        assert link_name in self._urdf.link_map.keys(), "given link_name does not appear in URDF"

        quat = Quaternion(0., 0., 0., 1.)
        if link_name == self._urdf.get_root(): return quat

        for joint in self._urdf.joints:

            xyz, rpy = self.get_joint_origin(joint)

            if joint.type == 'fixed':
                quat = quat * Quaternion.fromrpy(rpy)
                continue

            joint_index = self.actuated_joint_names.index(joint.name)
            qi = q[joint_index]

            if joint.type in {'revolute', 'continuous'}:
                quat = quat * Quaternion.fromrpy(rpy)
                quat = quat * Quaternion.fromangvec(qi, self.get_joint_axis(joint))

            else:
                raise NotImplementedError(f"{joint.type} joints are currently not supported")
            if joint.child == link_name:
                break

        return quat.getquat()

    @vectorize_args
    def get_geometric_jacobian(self, link_name, q):
        """Get the geometric jacobian matrix for a given link and joint state q"""

        #
        # TODO: allow user to compute jacobian in any frame (i.e. not
        # only the root link).
        #

        e = self.get_global_link_position(link_name, q)

        w = cs.DM.zeros(3)
        pdot = cs.DM.zeros(3)

        R = I3()

        joint_index_order = []
        jacobian_columns = []

        for joint in self._urdf.joints:

            xyz, rpy = self.get_joint_origin(joint)

            if joint.type == 'fixed':
                R = R @ rpy2r(rpy)
                continue

            joint_index = self.actuated_joint_names.index(joint.name)
            joint_index_order.append(joint_index)
            qi = q[joint_index]

            if joint.type in {'revolute', 'continuous'}:

                axis = self.get_joint_axis(joint)

                R = R @ rpy2r(rpy)
                R = R @ angvec2r(qi, axis)
                p = self.get_global_link_position(joint.child, q)

                z = R @ axis
                pdot = cs.cross(z, e - p)

                jcol = cs.vertcat(pdot, z)
                jacobian_columns.append(jcol)

            else:
                raise NotImplementedError(f"{joint.type} joints are currently not supported")

        # Sort columns of jacobian
        jacobian_columns_ordered = [jacobian_columns[idx] for idx in joint_index_order]

        # Build jacoian array
        J = jacobian_columns_ordered.pop(0)
        while jacobian_columns_ordered:
            J = cs.horzcat(J, jacobian_columns_ordered.pop(0))

        return J
