// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title SecureHealthRegistry
 * @dev Lightweight Ethereum Smart Contract for SecureHealth Chain
 * Handles tamper-evident storage for:
 * 1. Hospital Registry & Multi-Hospital Decentralized Nodes
 * 2. Doctor Identity & Medical License Verification Hashes
 * 3. Electronic Health Record (EHR) SHA-256 Hashes & Timestamps
 * 4. Head-Doctor Verified Federated Learning (FL) Model Updates
 * 5. Multi-Hospital FedAvg Global Model Distribution
 */
contract SecureHealthRegistry {
    address public owner;

    // ==========================================
    // DATA STRUCTURES
    // ==========================================

    // Hospital Node Registration
    struct Hospital {
        string hospitalId;
        string hospitalName;
        bytes32 hospitalHash; // SHA-256 of hospital credentials & node identity
        address nodeAddress;
        uint256 registeredAt;
        bool isRegistered;
    }

    // Doctor Identity & License
    struct Doctor {
        string doctorId;
        string hospitalId;
        string doctorName;
        string specialty;
        string licenseNumber;
        bytes32 doctorHash; // SHA-256 of doctor identity, license & hospital
        bool isHeadDoctor;
        bool isVerified;
        uint256 registeredAt;
    }

    // EHR Record Metadata
    struct EHRRecord {
        bytes32 recordHash;
        address recordedBy;
        string doctorId;
        string hospitalId;
        uint256 timestamp;
        bool exists;
    }

    // Verified FL Model Update Contribution
    struct VerifiedModelUpdate {
        uint256 roundNumber;
        string hospitalId;
        string doctorId;
        string headDoctorId;
        bytes32 modelHash;
        bytes32 headDoctorSignatureHash;
        address nodeAddress;
        uint256 timestamp;
        bool isApprovedByHeadDoctor;
    }

    // ==========================================
    // MAPPINGS
    // ==========================================

    // Hospital ID => Hospital Details
    mapping(string => Hospital) private hospitals;
    string[] public registeredHospitalIds;

    // Doctor ID => Doctor Details
    mapping(string => Doctor) private doctors;

    // Hospital ID => Array of Doctor IDs
    mapping(string => string[]) private hospitalDoctors;

    // EHR Record UUID => EHR Record Details
    mapping(string => EHRRecord) private ehrRecords;

    // Round Number => Array of Verified Model Updates
    mapping(uint256 => VerifiedModelUpdate[]) private flRoundUpdates;

    // Round Number => Global Aggregated Model Hash
    mapping(uint256 => bytes32) public globalModelHashes;

    // ==========================================
    // EVENTS
    // ==========================================

    event HospitalRegistered(string indexed hospitalId, string hospitalName, bytes32 hospitalHash, uint256 timestamp);
    event DoctorRegistered(string indexed doctorId, string indexed hospitalId, string doctorName, string specialty, bytes32 doctorHash, bool isHeadDoctor, uint256 timestamp);
    event EHRRegistered(string indexed recordUUID, bytes32 indexed recordHash, address indexed recordedBy, uint256 timestamp);
    event ModelUpdateSubmitted(uint256 indexed roundNumber, string indexed hospitalId, string doctorId, bytes32 modelHash, bytes32 headDoctorSigHash, uint256 timestamp);
    event GlobalModelPublished(uint256 indexed roundNumber, bytes32 globalModelHash, uint256 timestamp);

    modifier onlyOwner() {
        require(msg.sender == owner, "Caller is not contract owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    // ==========================================
    // 1. HOSPITAL REGISTRATION & VERIFICATION
    // ==========================================

    function registerHospital(
        string memory _hospitalId,
        string memory _hospitalName,
        bytes32 _hospitalHash
    ) public returns (bool) {
        require(!hospitals[_hospitalId].isRegistered, "Hospital already registered");
        require(_hospitalHash != bytes32(0), "Invalid hospital hash");

        hospitals[_hospitalId] = Hospital({
            hospitalId: _hospitalId,
            hospitalName: _hospitalName,
            hospitalHash: _hospitalHash,
            nodeAddress: msg.sender,
            registeredAt: block.timestamp,
            isRegistered: true
        });

        registeredHospitalIds.push(_hospitalId);
        emit HospitalRegistered(_hospitalId, _hospitalName, _hospitalHash, block.timestamp);
        return true;
    }

    function isHospitalRegistered(string memory _hospitalId)
        public
        view
        returns (bool isRegistered, string memory hospitalName, bytes32 hospitalHash, address nodeAddress)
    {
        Hospital memory h = hospitals[_hospitalId];
        return (h.isRegistered, h.hospitalName, h.hospitalHash, h.nodeAddress);
    }

    // ==========================================
    // 2. DOCTOR IDENTITY & LICENSE VERIFICATION
    // ==========================================

    function registerDoctor(
        string memory _doctorId,
        string memory _hospitalId,
        string memory _doctorName,
        string memory _specialty,
        string memory _licenseNumber,
        bytes32 _doctorHash,
        bool _isHeadDoctor
    ) public returns (bool) {
        require(hospitals[_hospitalId].isRegistered, "Hospital not registered on blockchain");
        require(!doctors[_doctorId].isVerified, "Doctor already registered");
        require(_doctorHash != bytes32(0), "Invalid doctor hash");

        doctors[_doctorId] = Doctor({
            doctorId: _doctorId,
            hospitalId: _hospitalId,
            doctorName: _doctorName,
            specialty: _specialty,
            licenseNumber: _licenseNumber,
            doctorHash: _doctorHash,
            isHeadDoctor: _isHeadDoctor,
            isVerified: true,
            registeredAt: block.timestamp
        });

        hospitalDoctors[_hospitalId].push(_doctorId);
        emit DoctorRegistered(_doctorId, _hospitalId, _doctorName, _specialty, _doctorHash, _isHeadDoctor, block.timestamp);
        return true;
    }

    function isDoctorVerified(string memory _doctorId, string memory _hospitalId)
        public
        view
        returns (
            bool isVerified,
            string memory doctorName,
            string memory specialty,
            string memory licenseNumber,
            bytes32 doctorHash,
            bool isHeadDoctor
        )
    {
        Doctor memory d = doctors[_doctorId];
        bool valid = d.isVerified && (keccak256(bytes(d.hospitalId)) == keccak256(bytes(_hospitalId)));
        return (valid, d.doctorName, d.specialty, d.licenseNumber, d.doctorHash, d.isHeadDoctor);
    }

    // ==========================================
    // 3. EHR RECORD ANCHORING & VERIFICATION
    // ==========================================

    function registerEHR(
        string memory _recordUUID,
        bytes32 _recordHash,
        string memory _doctorId,
        string memory _hospitalId
    ) public returns (bool) {
        require(!ehrRecords[_recordUUID].exists, "EHR Record already registered on blockchain");
        require(_recordHash != bytes32(0), "Invalid record hash");
        require(hospitals[_hospitalId].isRegistered, "Hospital unverified on blockchain");
        require(doctors[_doctorId].isVerified, "Doctor unverified on blockchain");

        ehrRecords[_recordUUID] = EHRRecord({
            recordHash: _recordHash,
            recordedBy: msg.sender,
            doctorId: _doctorId,
            hospitalId: _hospitalId,
            timestamp: block.timestamp,
            exists: true
        });

        emit EHRRegistered(_recordUUID, _recordHash, msg.sender, block.timestamp);
        return true;
    }

    function verifyEHR(string memory _recordUUID, bytes32 _incomingHash)
        public
        view
        returns (bool isValid, uint256 timestamp, address recordedBy, string memory doctorId, string memory hospitalId)
    {
        require(ehrRecords[_recordUUID].exists, "Record does not exist on blockchain");
        EHRRecord memory record = ehrRecords[_recordUUID];
        isValid = (record.recordHash == _incomingHash);
        return (isValid, record.timestamp, record.recordedBy, record.doctorId, record.hospitalId);
    }

    function getEHR(string memory _recordUUID)
        public
        view
        returns (bytes32 recordHash, address recordedBy, uint256 timestamp)
    {
        require(ehrRecords[_recordUUID].exists, "Record does not exist");
        EHRRecord memory record = ehrRecords[_recordUUID];
        return (record.recordHash, record.recordedBy, record.timestamp);
    }

    // ==========================================
    // 4. MULTI-HOSPITAL & HEAD-DOCTOR MODEL VERIFICATION
    // ==========================================

    function submitVerifiedModelUpdate(
        uint256 _round,
        string memory _hospitalId,
        string memory _doctorId,
        string memory _headDoctorId,
        bytes32 _modelHash,
        bytes32 _headDoctorSigHash
    ) public returns (bool) {
        require(hospitals[_hospitalId].isRegistered, "Hospital unverified on blockchain");
        require(doctors[_doctorId].isVerified, "Doctor unverified on blockchain");
        require(doctors[_headDoctorId].isVerified && doctors[_headDoctorId].isHeadDoctor, "Head Doctor signature unverified on blockchain");
        require(_modelHash != bytes32(0), "Invalid model update hash");
        require(_headDoctorSigHash != bytes32(0), "Invalid Head Doctor approval signature hash");

        flRoundUpdates[_round].push(
            VerifiedModelUpdate({
                roundNumber: _round,
                hospitalId: _hospitalId,
                doctorId: _doctorId,
                headDoctorId: _headDoctorId,
                modelHash: _modelHash,
                headDoctorSignatureHash: _headDoctorSigHash,
                nodeAddress: msg.sender,
                timestamp: block.timestamp,
                isApprovedByHeadDoctor: true
            })
        );

        emit ModelUpdateSubmitted(_round, _hospitalId, _doctorId, _modelHash, _headDoctorSigHash, block.timestamp);
        return true;
    }

    function verifyHospitalAndDoctorModel(
        string memory _hospitalId,
        string memory _doctorId,
        string memory _headDoctorId,
        bytes32 _modelHash
    ) public view returns (
        bool isHospitalValid,
        bool isDoctorValid,
        bool isHeadDoctorValid,
        bool isModelHashCommitted
    ) {
        isHospitalValid = hospitals[_hospitalId].isRegistered;
        isDoctorValid = doctors[_doctorId].isVerified && (keccak256(bytes(doctors[_doctorId].hospitalId)) == keccak256(bytes(_hospitalId)));
        isHeadDoctorValid = doctors[_headDoctorId].isVerified && doctors[_headDoctorId].isHeadDoctor && (keccak256(bytes(doctors[_headDoctorId].hospitalId)) == keccak256(bytes(_hospitalId)));

        // Check if model update is recorded
        isModelHashCommitted = false;
        // Search through current round updates
        for (uint256 r = 0; r < 50; r++) {
            for (uint256 i = 0; i < flRoundUpdates[r].length; i++) {
                if (flRoundUpdates[r][i].modelHash == _modelHash) {
                    isModelHashCommitted = true;
                    break;
                }
            }
            if (isModelHashCommitted) break;
        }

        return (isHospitalValid, isDoctorValid, isHeadDoctorValid, isModelHashCommitted);
    }

    function publishGlobalModel(uint256 _round, bytes32 _globalHash) public onlyOwner {
        require(_globalHash != bytes32(0), "Invalid global model hash");
        globalModelHashes[_round] = _globalHash;
        emit GlobalModelPublished(_round, _globalHash, block.timestamp);
    }

    function getRegisteredHospitalsCount() public view returns (uint256) {
        return registeredHospitalIds.length;
    }
}
